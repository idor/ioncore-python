#!/usr/bin/env python

"""
@file ion/integration/app_integration_service.py
@author David Everett
@brief Core service frontend for Application Integration Services 
"""

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)
from twisted.internet import defer

from ion.core.object import object_utils
from ion.core.process.process import ProcessFactory
from ion.core.process.service_process import ServiceProcess, ServiceClient
from ion.services.coi.resource_registry_beta.resource_client import ResourceClient
from ion.core.messaging.message_client import MessageClient

# import GPB type identifiers for AIS
from ion.integration.ais.ais_object_identifiers import AIS_REQUEST_MSG_TYPE, \
                                                       AIS_RESPONSE_ERROR_TYPE
from ion.integration.ais.ais_object_identifiers import UPDATE_USER_EMAIL_TYPE, UPDATE_USER_DISPATCH_QUEUE_TYPE
from ion.integration.ais.ais_object_identifiers import FIND_DATA_RESOURCES_REQ_MSG_TYPE

# import working classes for AIS
from ion.integration.ais.findDataResources.findDataResources import FindDataResources
from ion.integration.ais.getDataResourceDetail.getDataResourceDetail import GetDataResourceDetail
from ion.integration.ais.createDownloadURL.createDownloadURL import CreateDownloadURL
from ion.integration.ais.RegisterUser.RegisterUser import RegisterUser
from ion.integration.ais.ManageResources.ManageResources import ManageResources
from ion.integration.ais.manage_data_resource.manage_data_resource import ManageDataResource
from ion.integration.ais.manage_data_resource_subscription.manage_data_resource_subscription import ManageDataResourceSubscription


addresslink_type = object_utils.create_type_identifier(object_id=20003, version=1)
person_type = object_utils.create_type_identifier(object_id=20001, version=1)


class AppIntegrationService(ServiceProcess):
    """
    Service to provide clients access to backend data
    """
    # Declaration of service
    declare = ServiceProcess.service_declare(name='app_integration',
                                             version='0.1.0',
                                             dependencies=[])

    def __init__(self, *args, **kwargs):

        ServiceProcess.__init__(self, *args, **kwargs)

        self.rc = ResourceClient(proc = self)
        self.mc = MessageClient(proc = self)
    
        log.debug('AppIntegrationService.__init__()')

    def slc_init(self):
        pass

    @defer.inlineCallbacks
    def op_findDataResources(self, content, headers, msg):
        """
        @brief Find data resources that have been published, regardless
        of owner.
        @param GPB optional spatial and temporal bounds.
        @retval GPB with list of resource IDs.
        """

        log.debug('op_findDataResources service method.')
        try:
            # Instantiate the worker class
            worker = FindDataResources(self)
            returnValue = yield worker.findDataResources(content)
            yield self.reply_ok(msg, returnValue)

        except KeyError:
            estr = 'Missing information in message!'
            log.exception(estr)
            yield self.reply_err(msg, estr)

        return

    @defer.inlineCallbacks
    def op_findDataResourcesByUser(self, content, headers, msg):
        """
        @brief Find data resources associated with given userID,
        regardless of life cycle state.
        @param GPB containing OOID user ID, and option spatial and temporal
        bounds.
        @retval GPB with list of resource IDs.
        """

        log.debug('op_findDataResourcesByUser service method.')
        try:
            # Instantiate the worker class
            worker = FindDataResources(self)
            returnValue = yield worker.findDataResourcesByUser(content)
            yield self.reply_ok(msg, returnValue)

        except KeyError:
            estr = 'Missing information in message!'
            log.exception(estr)
            yield self.reply_err(msg, estr)

        return

    @defer.inlineCallbacks
    def op_getDataResourceDetail(self, content, headers, msg):
        """
        @brief Get detailed metadata for a given resource ID.
        @param GPB containing resource ID.
        @retval GPB containing detailed metadata.
        """

        log.info('op_getDataResourceDetail service method')
        try:
            worker = GetDataResourceDetail(self)
            returnValue = yield worker.getDataResourceDetail(content)
            yield self.reply_ok(msg, returnValue)

        except KeyError:
            estr = 'Missing information in message!'
            log.exception(estr)
            yield self.reply_err(msg, estr)

        return

    @defer.inlineCallbacks
    def op_createDownloadURL(self, content, headers, msg):
        """
        @brief Create download URL for given resource ID.
        @param GPB containing resource ID.
        @retval GPB containing download URL.
        """

        log.info('op_createDownloadURL: '+str(content))
        try:
            worker = CreateDownloadURL(self)
            returnValue = yield worker.createDownloadURL(content)
            yield self.reply_ok(msg, returnValue)   

        except KeyError:
            estr = 'Missing information in message!'
            log.exception(estr)
            yield self.reply_err(msg, estr)
            return
        
        return

    @defer.inlineCallbacks
    def op_registerUser(self, content, headers, msg):
        log.debug('op_registerUser: \n'+str(content))
        worker = RegisterUser(self)
        log.debug('op_registerUser: calling worker')
        response = yield worker.registerUser(content);
        yield self.reply_ok(msg, response)
        
    @defer.inlineCallbacks
    def op_updateUserEmail(self, content, headers, msg):
        log.debug('op_updateUserEmail: \n'+str(content))
        worker = RegisterUser(self)
        log.debug('op_updateUserEmail: calling worker')
        response = yield worker.updateUserEmail(content);
        yield self.reply_ok(msg, response)
        
    @defer.inlineCallbacks
    def op_updateUserDispatcherQueue(self, content, headers, msg):
        log.debug('op_updateUserDispatcherQueue: \n'+str(content))
        worker = RegisterUser(self)
        log.debug('op_updateUserDispatcherQueue: calling worker')
        response = yield worker.updateUserDispatcherQueue(content);
        yield self.reply_ok(msg, response)

    def getTestDatasetID(self):
        return self.dsID
                         
    @defer.inlineCallbacks
    def op_getResourceTypes(self, content, headers, msg):
        log.debug('op_getResourceTypes: \n'+str(content))
        worker = ManageResources(self)
        log.debug('op_getResourceTypes: calling worker')
        response = yield worker.getResourceTypes(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_getResourcesOfType(self, content, headers, msg):
        log.debug('op_getResourcesOfType: \n'+str(content))
        worker = ManageResources(self)
        log.debug('op_getResourcesOfType: calling worker')
        response = yield worker.getResourcesOfType(content);
        yield self.reply_ok(msg, response)


    @defer.inlineCallbacks
    def op_getResource(self, content, headers, msg):
        log.debug('op_getResource: \n'+str(content))
        worker = ManageResources(self)
        log.debug('op_getResource: calling worker')
        response = yield worker.getResource(content);
        yield self.reply_ok(msg, response)


    @defer.inlineCallbacks
    def op_createDataResource(self, content, headers, msg):
        """
        @brief create a new data resource
        """
        log.debug('op_createDataResource: \n'+str(content))
        worker = ManageDataResource(self)
        log.debug('op_createDataResource: calling worker')
        response = yield worker.create(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_updateDataResource(self, content, headers, msg):
        """
        @brief create a new data resource
        """
        log.debug('op_updateDataResource: \n'+str(content))
        worker = ManageDataResource(self)
        log.debug('op_updateDataResource: calling worker')
        response = yield worker.update(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_deleteDataResource(self, content, headers, msg):
        """
        @brief create a new data resource
        """
        log.debug('op_deleteDataResource: \n'+str(content))
        worker = ManageDataResource(self)
        log.debug('op_deleteDataResource: calling worker')
        response = yield worker.delete(content);
        yield self.reply_ok(msg, response)


    @defer.inlineCallbacks
    def op_createDataResourceSubscription(self, content, headers, msg):
        """
        @brief subscribe to a data resource
        """
        log.debug('op_createDataResourceSubscription: \n'+str(content))
        worker = ManageDataResourceSubscription(self)
        log.debug('op_createDataResourceSubscription: calling worker')
        response = yield worker.create(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_deleteDataResourceSubscription(self, content, headers, msg):
        """
        @brief delete subscription to a data resource
        """
        log.debug('op_deleteDataResourceSubscription: \n'+str(content))
        worker = ManageDataResourceSubscription(self)
        log.debug('op_deleteDataResourceSubscription: calling worker')
        response = yield worker.delete(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_updateDataResourceSubscription(self, content, headers, msg):
        """
        @brief update subscription to a data resource
        """
        log.debug('op_updateDataResourceSubscription: \n'+str(content))
        worker = ManageDataResourceSubscription(self)
        log.debug('op_updateDataResourceSubscription: calling worker')
        response = yield worker.update(content);
        yield self.reply_ok(msg, response)






class AppIntegrationServiceClient(ServiceClient):
    """
    This is a service client for AppIntegrationServices.
    """
    def __init__(self, proc=None, **kwargs):
        if not 'targetname' in kwargs:
            kwargs['targetname'] = "app_integration"
        ServiceClient.__init__(self, proc, **kwargs)
        self.mc = MessageClient(proc=proc)
        
    @defer.inlineCallbacks
    def findDataResources(self, message):
        yield self._check_init()
        result = yield self.CheckRequest(message)
        if result is not None:
            log.error('findDataResources: ' + result.error_str)
            defer.returnValue(result)
        log.debug("AppIntegrationServiceClient: findDataResources(): sending msg to AppIntegrationService.")
        (content, headers, payload) = yield self.rpc_send('findDataResources', message)
        log.info('Service reply: ' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def findDataResourcesByUser(self, message):
        yield self._check_init()
        result = yield self.CheckRequest(message)
        if result is not None:
            log.error('findDataResourcesByUser: ' + result.error_str)
            defer.returnValue(result)
        log.debug("AppIntegrationServiceClient: findDataResourcesByUser(): sending msg to AppIntegrationService.")
        (content, headers, payload) = yield self.rpc_send('findDataResourcesByUser', message)
        log.info('Service reply: ' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def getDataResourceDetail(self, message):
        yield self._check_init()
        result = yield self.CheckRequest(message)
        if result is not None:
            log.error('getDataResourceDetail: ' + result.error_str)
            defer.returnValue(result)
        log.debug("AppIntegrationServiceClient: getDataResourceDetail(): sending msg to AppIntegrationService.")
        (content, headers, payload) = yield self.rpc_send('getDataResourceDetail', message)
        log.info('Service reply: ' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def createDownloadURL(self, message):
        yield self._check_init()
        result = yield self.CheckRequest(message)
        if result is not None:
            defer.returnValue(result)
        # check that ooi_id is present in GPB
        if not message.message_parameters_reference.IsFieldSet('user_ooi_id'):
            # build AIS error response
            Response = yield self.mc.create_instance(AIS_RESPONSE_ERROR_TYPE, MessageName='AIS error response')
            Response.error_num = Response.ResponseCodes.BAD_REQUEST
            Response.error_str = "Required field [user_ooi_id] not found in message"
            log.error("Required field [user_ooi_id] not found in message")
            defer.returnValue(Response)
        log.debug("AppIntegrationServiceClient: createDownloadURL(): sending msg to AppIntegrationService.")
        (content, headers, payload) = yield self.rpc_send_protected('createDownloadURL',
                                                                    message,
                                                                    message.message_parameters_reference.user_ooi_id,
                                                                    "0")
        log.info('Service reply: ' + str(content))
        defer.returnValue(content)
 
    @defer.inlineCallbacks
    def registerUser(self, message):
        yield self._check_init()
        log.debug("AIS_client.registerUser: sending following message to registerUser:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send('registerUser', message)
        log.debug('AIS_client.registerUser: IR Service reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def updateUserEmail(self, message):
        yield self._check_init()
        # check that the GPB is correct type & has a payload
        result = yield self.CheckRequest(message)
        if result is not None:
            defer.returnValue(result)
       # check that ooi_id is present in GPB
        if not message.message_parameters_reference.IsFieldSet('user_ooi_id'):
            # build AIS error response
            Response = yield self.mc.create_instance(AIS_RESPONSE_ERROR_TYPE, MessageName='AIS error response')
            Response.error_num = Response.ResponseCodes.BAD_REQUEST
            Response.error_str = "Required field [user_ooi_id] not found in message"
            defer.returnValue(Response)
        log.debug("AIS_client.updateUserEmail: sending following message to updateUserEmail:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('updateUserEmail',
                                                                    message,
                                                                    message.message_parameters_reference.user_ooi_id,
                                                                    "0")
        log.debug('AIS_client.updateUserEmail: IR Service reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def updateUserDispatcherQueue(self, message):
        yield self._check_init()
        # check that the GPB is correct type & has a payload
        result = yield self.CheckRequest(message)
        if result is not None:
            defer.returnValue(result)
       # check that ooi_id is present in GPB
        if not message.message_parameters_reference.IsFieldSet('user_ooi_id'):
            # build AIS error response
            Response = yield self.mc.create_instance(AIS_RESPONSE_ERROR_TYPE, MessageName='AIS error response')
            Response.error_num = Response.ResponseCodes.BAD_REQUEST
            Response.error_str = "Required field [user_ooi_id] not found in message"
            defer.returnValue(Response)
        log.debug("AIS_client.updateUserDispatcherQueue: sending following message to updateUserDispatcherQueue:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('updateUserDispatcherQueue',
                                                                    message,
                                                                    message.message_parameters_reference.user_ooi_id,
                                                                    "0")
        log.debug('AIS_client.updateUserDispatcherQueue: IR Service reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def getResourceTypes(self, message):
        yield self._check_init()
        log.debug("AIS_client.getResourceTypes: sending following message to getResourceTypes:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send('getResourceTypes', message)
        log.debug('AIS_client.getResourceTypes: AIS reply:\n' + str(content))
        defer.returnValue(content)
 
    @defer.inlineCallbacks
    def getResourcesOfType(self, message):
        yield self._check_init()
        log.debug("AIS_client.getResourcesOfType: sending following message to getResourcesOfType:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send('getResourcesOfType', message)
        log.debug('AIS_client.getResourcesOfType: AIS reply:\n' + str(content))
        defer.returnValue(content)
 
    @defer.inlineCallbacks
    def getResource(self, message):
        yield self._check_init()
        log.debug("AIS_client.getResource: sending following message to getResource:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send('getResource', message)
        log.debug('AIS_client.getResource: AIS reply:\n' + str(content))
        defer.returnValue(content)
 
    @defer.inlineCallbacks
    def createDataResource(self, message):
        yield self._check_init()
        log.debug("AIS_client.createDataResource: sending following message to createDataResource:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send('createDataResource', message)
        log.debug('AIS_client.createDataResource: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def updateDataResource(self, message):
        yield self._check_init()
        log.debug("AIS_client.updateDataResource: sending following message to updateDataResource:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send('updateDataResource', message)
        log.debug('AIS_client.updateDataResource: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def deleteDataResource(self, message):
        yield self._check_init()
        log.debug("AIS_client.deleteDataResource: sending following message to deleteDataResource:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send('deleteDataResource', message)
        log.debug('AIS_client.deleteDataResource: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def createDataResourceSubscription(self, message):
        yield self._check_init()
        log.debug("AIS_client.createDataResourceSubscription: sending following message:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send('createDataResourceSubscription', message)
        log.debug('AIS_client.createDataResourceSubscription: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def deleteDataResourceSubscription(self, message):
        yield self._check_init()
        log.debug("AIS_client.deleteDataResourceSubscription: sending following message:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send('deleteDataResourceSubscription', message)
        log.debug('AIS_client.deleteDataResourceSubscription: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def updateDataResourceSubscription(self, message):
        yield self._check_init()
        log.debug("AIS_client.updateDataResourceSubscription: sending following message:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send('updateDataResourceSubscription', message)
        log.debug('AIS_client.updateDataResourceSubscription: AIS reply:\n' + str(content))
        defer.returnValue(content)
        

    @defer.inlineCallbacks
    def CheckRequest(self, request):
        # Check for correct request protocol buffer type
        if request.MessageType != AIS_REQUEST_MSG_TYPE:
            # build AIS error response
            Response = yield self.mc.create_instance(AIS_RESPONSE_ERROR_TYPE, MessageName='AIS error response')
            Response.error_num = Response.ResponseCodes.BAD_REQUEST
            Response.error_str = 'Bad message type receieved, ignoring'
            defer.returnValue(Response)

        # Check payload in message
        if not request.IsFieldSet('message_parameters_reference'):
            # build AIS error response
            Response = yield self.mc.create_instance(AIS_RESPONSE_ERROR_TYPE, MessageName='AIS error response')
            Response.error_num = Response.ResponseCodes.BAD_REQUEST
            Response.error_str = "Required field [message_parameters_reference] not found in message"
            defer.returnValue(Response)
  
        defer.returnValue(None)


# Spawn of the process using the module name
factory = ProcessFactory(AppIntegrationService)
