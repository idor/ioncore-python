#!/usr/bin/env python

"""
@file ion/integration/ais/findDataResources/findDataResources.py
@author David Everett
@brief Worker class to find resources for a given user id, bounded by
spacial and temporal parameters.
"""

import time, datetime
import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)
from twisted.internet import defer

from decimal import Decimal

from ion.services.coi.resource_registry.resource_client import ResourceClient, ResourceClientError
from ion.services.coi.resource_registry.association_client import AssociationClient, AssociationInstance, AssociationManager
from ion.services.coi.resource_registry.association_client import AssociationClientError
from ion.services.coi.datastore import DataStoreWorkBenchError

from ion.integration.ais.common.spatial_temporal_bounds import SpatialTemporalBounds
from ion.integration.ais.findDataResources.resourceStubs import DatasetControllerClient
from ion.services.dm.inventory.association_service import AssociationServiceClient, AssociationServiceError
from ion.services.dm.inventory.association_service import PREDICATE_OBJECT_QUERY_TYPE, SUBJECT_PREDICATE_QUERY_TYPE, IDREF_TYPE
from ion.services.coi.datastore_bootstrap.ion_preload_config import ROOT_USER_ID, HAS_A_ID, IDENTITY_RESOURCE_TYPE_ID, TYPE_OF_ID, ANONYMOUS_USER_ID, HAS_LIFE_CYCLE_STATE_ID, OWNED_BY_ID, \
            SAMPLE_PROFILE_DATASET_ID, DATASET_RESOURCE_TYPE_ID, DATASOURCE_RESOURCE_TYPE_ID


from ion.core.object import object_utils
ASSOCIATION_TYPE = object_utils.create_type_identifier(object_id=13, version=1)
PREDICATE_REFERENCE_TYPE = object_utils.create_type_identifier(object_id=25, version=1)
LCS_REFERENCE_TYPE = object_utils.create_type_identifier(object_id=26, version=1)

# import GPB type identifiers for AIS
from ion.integration.ais.ais_object_identifiers import AIS_RESPONSE_MSG_TYPE, \
                                                       AIS_RESPONSE_ERROR_TYPE
from ion.integration.ais.ais_object_identifiers import FIND_DATA_RESOURCES_RSP_MSG_TYPE, \
                                                       FIND_DATA_RESOURCES_BY_OWNER_RSP_MSG_TYPE

DNLD_BASE_THREDDS_URL = 'http://localhost:8081/thredds'
DNLD_DIR_PATH = '/dodsC/scanData/'
DNLD_FILE_TYPE = '.ncml'

class FindDataResources(object):

    #
    # these are the mappings from resource life cycle states to the view
    # permission states of a dataset
    # 
    REGISTERED = 'Registered'
    PRIVATE    = 'Private'
    PUBLIC     = 'Public'
    UNKOWNN    = 'Unknown'
    
    def __init__(self, ais):
        log.info('FindDataResources.__init__()')
        self.ais = ais
        self.rc = ResourceClient(proc=ais)
        self.mc = ais.mc
        #self.dscc = DatasetControllerClient(proc=ais)
        self.asc = AssociationServiceClient()
        self.ac = AssociationClient(proc=ais)

    @defer.inlineCallbacks
    def findDataResources(self, msg):
        """
        Worker class method called by app_integration_service to implement
        findDataResources.  Finds all dataset resources that are "published"
        and returns their IDs along with a load of metadata.
        """

        log.debug('findDataResources Worker Class Method')

        #
        # I don't think this is needed, but leaving it in for now
        #
        userID = msg.message_parameters_reference.user_ooi_id

        self.downloadURL       = 'Uninitialized'
        
        #
        # Create the response message to which we will attach the list of
        # resource IDs
        #
        rspMsg = yield self.mc.create_instance(AIS_RESPONSE_MSG_TYPE)
        rspMsg.message_parameters_reference.add()
        rspMsg.message_parameters_reference[0] = rspMsg.CreateObject(FIND_DATA_RESOURCES_RSP_MSG_TYPE)

        # Get the list of dataset resource IDs
        dSetResults = yield self.__findResourcesOfType(DATASET_RESOURCE_TYPE_ID)
        if dSetResults == None:
            log.error('Error finding resources.')
            Response = yield self.mc.create_instance(AIS_RESPONSE_ERROR_TYPE,
                                  MessageName='AIS findDataResources error response')
            Response.error_num = Response.ResponseCodes.NOT_FOUND
            Response.error_str = "No DatasetIDs were found."
            defer.returnValue(Response)
            
        log.debug('Found ' + str(len(dSetResults.idrefs)) + ' datasets.')

        yield self.__getDataResources(msg, dSetResults, rspMsg)

        defer.returnValue(rspMsg)


    @defer.inlineCallbacks
    def findDataResourcesByUser(self, msg):
        """
        Worker class method called by app_integration_service to implement
        findDataResourcesByUser.  Finds all dataset resources regardless of state
        and returns their IDs along with a load of metadata.
        """

        log.debug('findDataResourcesByUser Worker Class Method')

        if msg.message_parameters_reference.IsFieldSet('user_ooi_id'):
            userID = msg.message_parameters_reference.user_ooi_id
        else:
            Response = yield self.mc.create_instance(AIS_RESPONSE_ERROR_TYPE,
                                  MessageName='AIS findDataResourcesByUser error response')
            Response.error_num = Response.ResponseCodes.BAD_REQUEST
            Response.error_str = "Required field [user_ooi_id] not found in message"
            defer.returnValue(Response)

        self.downloadURL       = 'Uninitialized'
        
        #
        # Create the response message to which we will attach the list of
        # resource IDs
        #
        rspMsg = yield self.mc.create_instance(AIS_RESPONSE_MSG_TYPE)
        rspMsg.message_parameters_reference.add()
        rspMsg.message_parameters_reference[0] = rspMsg.CreateObject(FIND_DATA_RESOURCES_BY_OWNER_RSP_MSG_TYPE)

        # Get the list of dataset resource IDs
        dSetResults = yield self.__findResourcesOfTypeAndOwner(DATASET_RESOURCE_TYPE_ID, userID)
        if dSetResults == None:
            log.error('Error finding resources.')
            Response = yield self.mc.create_instance(AIS_RESPONSE_ERROR_TYPE,
                                  MessageName='AIS findDataResources error response')
            Response.error_num = Response.ResponseCodes.NOT_FOUND
            Response.error_str = "No DatasetIDs were found."
            defer.returnValue(Response)
        
        log.debug('Found ' + str(len(dSetResults.idrefs)) + ' datasets.')

        yield self.__getDataResources(msg, dSetResults, rspMsg, userID)
        
        defer.returnValue(rspMsg)


    @defer.inlineCallbacks
    def getAssociatedSource(self, dSetResID):
        """
        Worker class method to get the data source that associated with a given
        data set.  This is a public method because it can be called from the
        findDataResourceDetail worker class.
        """
        log.debug('getAssociatedSource()')

        try: 
            ds = yield self.rc.get_instance(dSetResID)
            
        except ResourceClientError:    
            log.error('AssociationError')
            defer.returnValue(None)

        try:
            results = yield self.ac.find_associations(obj=ds, predicate_or_predicates=HAS_A_ID)

        except AssociationClientError:
            log.error('AssociationError')
            defer.returnValue(None)

        for association in results:
            log.debug('Associated Source for Dataset: ' + \
                      association.ObjectReference.key + \
                      ' is: ' + association.SubjectReference.key)

        defer.returnValue(association.SubjectReference.key)

                      
    @defer.inlineCallbacks
    def getAssociatedOwner(self, dsID):
        """
        Worker class method to find the owner associated with a data set.
        This is a public method because it can be called from the
        findDataResourceDetail worker class.
        """
        log.debug('getAssociatedOwner()')

        request = yield self.mc.create_instance(SUBJECT_PREDICATE_QUERY_TYPE)

        #
        # Set up an owned_by_id search term using:
        # - OWNED_BY_ID as predicate
        # - LCS_REFERENCE_TYPE object set to ACTIVE as object
        #
        pair = request.pairs.add()

        # ..(predicate)
        pref = request.CreateObject(PREDICATE_REFERENCE_TYPE)
        pref.key = OWNED_BY_ID

        pair.predicate = pref

        # ..(subject)
        type_ref = request.CreateObject(IDREF_TYPE)
        type_ref.key = dsID
        
        pair.subject = type_ref

        log.info('Calling get_objects with dsID: ' + dsID)

        try:
            result = yield self.asc.get_objects(request)
        
        except AssociationServiceError:
            log.error('getAssociatedOwner: association error!')
            defer.returnValue(None)

        if len(result.idrefs) == 0:
            log.error('Owner not found!')
            defer.returnValue('OWNER NOT FOUND!')
        elif len(result.idrefs) == 1:
            defer.returnValue(result.idrefs[0].key)
        else:
            log.error('More than 1 owner found!')
            defer.returnValue('MULTIPLE OWNERS!')


    @defer.inlineCallbacks
    def __getDataResources(self, msg, dSetResults, rspMsg, userID = None):
        """
        Given the list of datasetIDs, determine in the data represented by
        the dataset is within the given spatial and temporal bounds, and
        if so, add it to the response GPB.
        """

        #
        # Instantiate a bounds object, and load it up with the given bounds
        # info
        #
        bounds = SpatialTemporalBounds()
        bounds.loadBounds(msg.message_parameters_reference)
        
        #
        # Now iterate through the list if dataset resource IDs and for each ID:
        #   - get the dataset instance
        #   - get the associated datasource instance
        #   - check that spatial and temporal criteria are met:
        #   - if not:
        #     - continue
        #   - if so:
        #     - add the metadata to the response GPB
        #
        
        i = 0
        j = 0
        while i < len(dSetResults.idrefs):
            dSetResID = dSetResults.idrefs[i].key
            log.debug('Working on dataset: ' + dSetResID)
            
            dSet = yield self.rc.get_instance(dSetResID)
            if dSet is None:
                log.error('dSet is None')
                Response = yield self.mc.create_instance(AIS_RESPONSE_ERROR_TYPE,
                                      MessageName='AIS findDataResources error response')
                Response.error_num = Response.ResponseCodes.NOT_FOUND
                Response.error_str = "Dataset not found."
                defer.returnValue(Response)        

            minMetaData = {}
            self.__loadMinMetaData(dSet, minMetaData)

            #
            # If the dataset's data is within the given criteria, include it
            # in the list
            #
            if bounds.isInBounds(minMetaData):                

                dSourceResID = yield self.getAssociatedSource(dSetResID)
                if dSourceResID is None:
                    log.error('dSourceResID is None')
                    Response = yield self.mc.create_instance(AIS_RESPONSE_ERROR_TYPE,
                                          MessageName='AIS findDataResources error response')
                    Response.error_num = Response.ResponseCodes.NOT_FOUND
                    Response.error_str = "Datasource not found."
                    defer.returnValue(Response)        

                try:
                    dSource = yield self.rc.get_instance(dSourceResID)
                
                except ResourceClientError: 
                    log.error('ResourceClientError Exception!')
                    Response = yield self.mc.create_instance(AIS_RESPONSE_ERROR_TYPE,
                                          MessageName='AIS findDataResources error response')
                    Response.error_num = Response.ResponseCodes.NOT_FOUND
                    Response.error_str = "Datasource not found."
                    defer.returnValue(Response)        

                #
                # Added this for Tim and Tom; not sure we need it yet...
                #
                ownerID = yield self.getAssociatedOwner(dSetResID)

                self.__createDownloadURL(dSetResID)

                if userID is None:
                    #
                    # This was a findDataResources request
                    #
                    rspMsg.message_parameters_reference[0].dataResourceSummary.add()
                    rspMsg.message_parameters_reference[0].dataResourceSummary[j].notificationSet = False
                    rspMsg.message_parameters_reference[0].dataResourceSummary[j].date_registered = dSource.registration_datetime_millis
                    self.__loadRspPayload(rspMsg.message_parameters_reference[0].dataResourceSummary[j].datasetMetadata, minMetaData, ownerID, dSetResID)
                else:
                    #
                    # This was a findDataResourcesByUser request
                    #
                    rspMsg.message_parameters_reference[0].datasetByOwnerMetadata.add()
                    self.__loadRspByOwnerPayload(rspMsg.message_parameters_reference[0].datasetByOwnerMetadata[j], minMetaData, ownerID, dSet, dSource)


                #self.__printRootAttributes(dSet)
                #self.__printRootVariables(dSet)
                #self.__printSourceMetadata(dSource)
                #self.__printDownloadURL()
    
                j = j + 1
            else:
                log.debug("isInBounds is FALSE")

            
            i = i + 1


    @defer.inlineCallbacks
    def __findResourcesOfType(self, resourceType):

        request = yield self.mc.create_instance(PREDICATE_OBJECT_QUERY_TYPE)

        #
        # Set up a resource type search term using:
        # - TYPE_OF_ID as predicate
        # - object of type: resourceType parameter as object
        #
        pair = request.pairs.add()
    
        # ..(predicate)
        pref = request.CreateObject(PREDICATE_REFERENCE_TYPE)
        pref.key = TYPE_OF_ID

        pair.predicate = pref

        # ..(object)
        type_ref = request.CreateObject(IDREF_TYPE)
        type_ref.key = resourceType
        
        pair.object = type_ref

        # 
        # Set up a life cycle state term using:
        # - HAS_LIFE_CYCLE_STATE_ID as predicate
        # - LCS_REFERENCE_TYPE object set to ACTIVE as object
        #
        pair = request.pairs.add()

        # ..(predicate)
        pref = request.CreateObject(PREDICATE_REFERENCE_TYPE)
        pref.key = HAS_LIFE_CYCLE_STATE_ID

        pair.predicate = pref

        # ..(object)
        state_ref = request.CreateObject(LCS_REFERENCE_TYPE)
        state_ref.lcs = state_ref.LifeCycleState.ACTIVE
        pair.object = state_ref

        try:
            result = yield self.asc.get_subjects(request)

        except AssociationServiceError:
            log.error('__findResourcesOfType: association error!')
            defer.returnValue(None)

        
        defer.returnValue(result)

        
    @defer.inlineCallbacks
    def __findResourcesOfTypeAndOwner(self, resourceType, owner):

        request = yield self.mc.create_instance(PREDICATE_OBJECT_QUERY_TYPE)

        #
        # Set up an owned_by_id search term using:
        # - OWNED_BY_ID as predicate
        # - LCS_REFERENCE_TYPE object set to ACTIVE as object
        #
        pair = request.pairs.add()

        # ..(predicate)
        pref = request.CreateObject(PREDICATE_REFERENCE_TYPE)
        pref.key = OWNED_BY_ID

        pair.predicate = pref

        # ..(object)
        type_ref = request.CreateObject(IDREF_TYPE)
        type_ref.key = owner
        
        pair.object = type_ref

        #
        # Set up an owned_by_id search term using:
        # - TYPE_OF_ID as predicate
        # - object of type: resourceType parameter as object
        #
        pair = request.pairs.add()

        # ..(predicate)
        pref = request.CreateObject(PREDICATE_REFERENCE_TYPE)
        pref.key = TYPE_OF_ID

        pair.predicate = pref

        # ..(object)
        type_ref = request.CreateObject(IDREF_TYPE)
        type_ref.key = resourceType
        pair.object = type_ref
        
        log.info('Calling get_subjects with owner: ' + owner)

        try:
            result = yield self.asc.get_subjects(request)
        
        except AssociationServiceError:
            log.error('__findResourcesOfTypeAndOwner: association error!')
            defer.returnValue(None)
        
        defer.returnValue(result)


    def __loadMinMetaData(self, dSet, minMetaData):
        for attrib in dSet.root_group.attributes:
            #log.debug('Root Attribute: %s = %s'  % (str(attrib.name), str(attrib.GetValue())))
            if attrib.name == 'title':
                minMetaData['title'] = attrib.GetValue()
            elif attrib.name == 'institution':                
                minMetaData['institution'] = attrib.GetValue()
            elif attrib.name == 'source':                
                minMetaData['source'] = attrib.GetValue()
            elif attrib.name == 'references':                
                minMetaData['references'] = attrib.GetValue()
            elif attrib.name == 'ion_time_coverage_start':                
                minMetaData['ion_time_coverage_start'] = attrib.GetValue()
            elif attrib.name == 'ion_time_coverage_end':                
                minMetaData['ion_time_coverage_end'] = attrib.GetValue()
            elif attrib.name == 'summary':                
                minMetaData['summary'] = attrib.GetValue()
            elif attrib.name == 'comment':                
                minMetaData['comment'] = attrib.GetValue()
            elif attrib.name == 'ion_geospatial_lat_min':                
                minMetaData['ion_geospatial_lat_min'] = Decimal(str(attrib.GetValue()))
            elif attrib.name == 'ion_geospatial_lat_max':                
                minMetaData['ion_geospatial_lat_max'] = Decimal(str(attrib.GetValue()))
            elif attrib.name == 'ion_geospatial_lon_min':                
                minMetaData['ion_geospatial_lon_min'] = Decimal(str(attrib.GetValue()))
            elif attrib.name == 'ion_geospatial_lon_max':                
                minMetaData['ion_geospatial_lon_max'] = Decimal(str(attrib.GetValue()))
            elif attrib.name == 'ion_geospatial_vertical_min':                
                minMetaData['ion_geospatial_vertical_min'] = Decimal(str(attrib.GetValue()))
            elif attrib.name == 'ion_geospatial_vertical_max':                
                minMetaData['ion_geospatial_vertical_max'] = Decimal(str(attrib.GetValue()))
            elif attrib.name == 'ion_geospatial_vertical_positive':                
                minMetaData['ion_geospatial_vertical_positive'] = attrib.GetValue()


    def __printDownloadURL(self):
        log.debug('Download URL: ' + self.downloadURL)


    def __printRootAttributes(self, ds):
        for atrib in ds.root_group.attributes:
            log.debug('Root Attribute: %s = %s'  % (str(atrib.name), str(atrib.GetValue())))


    def __printRootVariables(self, ds):
        for var in ds.root_group.variables:
            log.debug('Root Variable: %s' % str(var.name))
            for atrib in var.attributes:
                log.debug("Attribute: %s = %s" % (str(atrib.name), str(atrib.GetValue())))
            print "....Dimensions:"
            for dim in var.shape:
                log.debug("    ....%s (%s)" % (str(dim.name), str(dim.length)))


    def __printSourceMetadata(self, dSource):
        log.debug('source_type: ' + str(dSource.source_type))
        for property in dSource.property:
            log.debug('Property: ' + property)
        for sid in dSource.station_id:
            log.debug('Station ID: ' + sid)
        log.debug('request_type: ' + str(dSource.request_type))
        log.debug('base_url: ' + dSource.base_url)
        log.debug('max_ingest_millis: ' + str(dSource.max_ingest_millis))


    def __loadRspPayload(self, rootAttributes, minMetaData, userID, dSetResID):
        rootAttributes.user_ooi_id = userID
        rootAttributes.data_resource_id = dSetResID
        rootAttributes.download_url = self.__createDownloadURL(dSetResID)
        for attrib in minMetaData:
            log.debug('Root Attribute: %s = %s'  % (attrib, minMetaData[attrib]))
            if  attrib == 'title':
                rootAttributes.title = minMetaData[attrib]
            elif attrib == 'institution':                
                rootAttributes.institution = minMetaData[attrib]
            elif attrib == 'source':                
                rootAttributes.source = minMetaData[attrib]
            elif attrib == 'references':                
                rootAttributes.references = minMetaData[attrib]
            elif attrib == 'ion_time_coverage_start':                
                rootAttributes.ion_time_coverage_start = minMetaData[attrib]
            elif attrib == 'ion_time_coverage_end':                
                rootAttributes.ion_time_coverage_end = minMetaData[attrib]
            elif attrib == 'summary':                
                rootAttributes.summary = minMetaData[attrib]
            elif attrib == 'comment':                
                rootAttributes.comment = minMetaData[attrib]
            elif attrib == 'ion_geospatial_lat_min':                
                rootAttributes.ion_geospatial_lat_min = float(minMetaData[attrib])
            elif attrib == 'ion_geospatial_lat_max':                
                rootAttributes.ion_geospatial_lat_max = float(minMetaData[attrib])
            elif attrib == 'ion_geospatial_lon_min':                
                rootAttributes.ion_geospatial_lon_min = float(minMetaData[attrib])
            elif attrib == 'ion_geospatial_lon_max':                
                rootAttributes.ion_geospatial_lon_max = float(minMetaData[attrib])
            elif attrib == 'ion_geospatial_vertical_min':                
                rootAttributes.ion_geospatial_vertical_min = float(minMetaData[attrib])
            elif attrib == 'ion_geospatial_vertical_max':                
                rootAttributes.ion_geospatial_vertical_max = float(minMetaData[attrib])
            elif attrib == 'ion_geospatial_vertical_positive':                
                rootAttributes.ion_geospatial_vertical_positive = minMetaData[attrib]


    def __createDownloadURL(self, dSetResID):
        #
        #  opendap URL for accessing the data.
        # The URL will be composed a couple parts:  <base_url_to_thredds> +
        # <directory_path> + <resourceid>.ncml
        #
        # http://localhost:8081/thredds/dodsC/scanData/<resID>.ncml
        #
        self.downloadURL =  DNLD_BASE_THREDDS_URL + \
                            DNLD_DIR_PATH + \
                            dSetResID + \
                            DNLD_FILE_TYPE
        
        return self.downloadURL

    def __loadRspByOwnerPayload(self, rspPayload, minMetaData, userID, dSet, dSource):
        rspPayload.data_resource_id = dSet.ResourceIdentity
        rspPayload.title = minMetaData['title']
        rspPayload.date_registered = dSource.registration_datetime_millis
        rspPayload.ion_title = dSource.ion_title
        #rspPayload.activation_state = dSource.ResourceLifeCycleState
        #
        # Set the activate state based on the resource lcs
        #
        if dSource.ResourceLifeCycleState == dSource.NEW:
            rspPayload.activation_state = self.REGISTERED
        elif dSource.ResourceLifeCycleState == dSource.ACTIVE:
            rspPayload.activation_state = self.PRIVATE
        elif dSource.ResourceLifeCycleState == dSource.COMMISSIONED:
            rspPayload.activation_state = self.PUBLIC
        else:
            rspPayload.activation_state = self.UNKNOWN
        rspPayload.update_interval_seconds = dSource.update_interval_seconds
        

