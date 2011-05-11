#!/usr/bin/env python

"""
@file ion/services/dm/ingestion/ingestion.py
@author Michael Meisinger
@author David Stuebe
@author Dave Foster <dfoster@asascience.com>
@author Tim LaRocque (client changes only)
@brief service for registering resources

To test this with the Java CC!
> scripts/start-cc -h amoeba.ucsd.edu -a sysname=eoitest res/scripts/eoi_demo.py
"""

import time, calendar
from ion.services.dm.distribution.events import DatasetSupplementAddedEventPublisher
import ion.util.ionlog
from twisted.internet import defer, reactor
from twisted.python import reflect

from ion.core.process.process import ProcessFactory
from ion.core.process.service_process import ServiceProcess, ServiceClient
import ion.util.procutils as pu

from ion.core.messaging.message_client import MessageClient
from ion.services.coi.resource_registry.resource_client import ResourceClient
from ion.services.dm.distribution.publisher_subscriber import Subscriber, PublisherFactory

from ion.core.exception import ApplicationError

# For testing - used in the client
from ion.services.dm.distribution.pubsub_service import PubSubClient, XS_TYPE, XP_TYPE, TOPIC_TYPE, SUBSCRIBER_TYPE
from ion.services.coi import datastore

from ion.core.exception import ReceivedApplicationError, ReceivedError, ReceivedContainerError

from ion.core.object.gpb_wrapper import OOIObjectError

from ion.core import ioninit
from ion.core.object import object_utils

CONF = ioninit.config(__name__)
log = ion.util.ionlog.getLogger(__name__)


CDM_DATASET_TYPE = object_utils.create_type_identifier(object_id=10001, version=1)

CDM_SINT_ARRAY_TYPE = object_utils.create_type_identifier(object_id=10009, version=1)
CDM_UINT_ARRAY_TYPE = object_utils.create_type_identifier(object_id=10010, version=1)
CDM_LSINT_ARRAY_TYPE = object_utils.create_type_identifier(object_id=10011, version=1)
CDM_LUINT_ARRAY_TYPE = object_utils.create_type_identifier(object_id=10012, version=1)

CDM_FLOAT_ARRAY_TYPE = object_utils.create_type_identifier(object_id=10013, version=1)
CDM_DOUBLE_ARRAY_TYPE = object_utils.create_type_identifier(object_id=10014, version=1)

CDM_STRING_ARRAY_TYPE = object_utils.create_type_identifier(object_id=10015, version=1)
CDM_OPAQUE_ARRAY_TYPE = object_utils.create_type_identifier(object_id=10016, version=1)

CDM_BOUNDED_ARRAY_TYPE = object_utils.create_type_identifier(object_id=10021, version=1)

SUPPLEMENT_MSG_TYPE = object_utils.create_type_identifier(object_id=2001, version=1)
PERFORM_INGEST_MSG_TYPE = object_utils.create_type_identifier(object_id=2002, version=1)
CREATE_DATASET_TOPICS_MSG_TYPE = object_utils.create_type_identifier(object_id=2003, version=1)
INGESTION_READY_TYPE = object_utils.create_type_identifier(object_id=2004, version=1)
DAQ_COMPLETE_MSG_TYPE = object_utils.create_type_identifier(object_id=2005, version=1)

BLOBS_MESSAGE_TYPE = object_utils.create_type_identifier(object_id=52, version=1)


class IngestionError(ApplicationError):
    """
    An error occured during the begin_ingest op of IngestionService.
    """
    pass


class IngestionService(ServiceProcess):
    """
    Place holder to move data between EOI and the datastore
    """

    # Declaration of service
    declare = ServiceProcess.service_declare(name='ingestion', version='0.1.0', dependencies=[])

    #TypeClassType = gpb_wrapper.get_type_from_obj(type_pb2.ObjectType())


    excluded_data_array_types = (CDM_SINT_ARRAY_TYPE, CDM_UINT_ARRAY_TYPE, CDM_LSINT_ARRAY_TYPE, CDM_LUINT_ARRAY_TYPE,
                                 CDM_DOUBLE_ARRAY_TYPE, CDM_FLOAT_ARRAY_TYPE, CDM_STRING_ARRAY_TYPE,
                                 CDM_OPAQUE_ARRAY_TYPE)

    def __init__(self, *args, **kwargs):
        # Service class initializer. Basic config, but no yields allowed.

        #assert isinstance(backend, store.IStore)
        #self.backend = backend
        ServiceProcess.__init__(self, *args, **kwargs)

        #self.push = self.workbench.push
        #self.pull = self.workbench.pull
        #self.fetch_blobs = self.workbench.fetch_blobs
        self.op_fetch_blobs = self.workbench.op_fetch_blobs

        self._defer_ingest = defer.Deferred()       # waited on by op_ingest to signal end of ingestion

        self.rc = ResourceClient(proc=self)
        self.mc = MessageClient(proc=self)

        self._pscclient = PubSubClient(proc=self)
        self._notify_ingest_factory = PublisherFactory(publisher_type=DatasetSupplementAddedEventPublisher,
                                                       process=self)

        self.dsc = datastore.DataStoreClient(proc=self)

        self.dataset = None

        log.info('IngestionService.__init__()')


    @defer.inlineCallbacks
    def op_create_dataset_topics(self, content, headers, msg):
        """
        Creates ingestion and notification topics that can be used to publish ingestion
        data and notifications about ingestion.
        """

        # @TODO: adapted from temp reg publisher code in publisher_subscriber, update as appropriate
        msg = yield self.mc.create_instance(XS_TYPE)

        msg.exchange_space_name = 'swapmeet'

        rc = yield self._pscclient.declare_exchange_space(msg)
        #self._xs_id = rc.id_list[0]

        msg = yield self.mc.create_instance(XP_TYPE)
        msg.exchange_point_name = 'science_data'
        msg.exchange_space_id = self._xs_id

        rc = yield self._pscclient.declare_exchange_point(msg)
        #self._xp_id = rc.id_list[0]

        msg = yield self.mc.create_instance(TOPIC_TYPE)
        msg.topic_name = content.dataset_id
        msg.exchange_space_id = self._xs_id
        msg.exchange_point_id = self._xp_id

        rc = yield self._pscclient.declare_topic(msg)

        yield self.reply_ok(msg)

    class IngestSubscriber(Subscriber):
        """
        Specially derived Subscriber that routes received messages into the ingest service's
        standard receive method, as if it is one of the process receivers.
        """

        @defer.inlineCallbacks
        def _receive_handler(self, content, msg):
            yield self._process.receive(content, msg)

    def _ingest_data_topic_valid(self, ingest_data_topic):
        """
        Determines if the ingestion data topic is a valid topic for ingestion.
        The topic should have been registered via op_create_dataset_topics prior to
        ingestion.
        @TODO: this
        """
        log.debug("TODO: _ingest_data_topic_valid")
        return True

    @defer.inlineCallbacks
    def _prepare_ingest(self, content):
        """
        Factor out the preparation for ingestion so that we can unit test functionality
        """

        # Get the current state of the dataset:
        self.dataset = yield self.rc.get_instance(content.dataset_id, excluded_types=[CDM_BOUNDED_ARRAY_TYPE])

        ba_links = []
        for var in self.dataset.root_group.variables:
            var_links = var.content.bounded_arrays.GetLinks()
            ba_links.extend(var_links)

        self.dataset.Repository.fetch_links(ba_links)



        # TODO: replace this from the msg itself with just dataset id
        ingest_data_topic = content.dataset_id

        # TODO: validate ingest_data_topic
        valid = self._ingest_data_topic_valid(ingest_data_topic)
        if not valid:
            log.error("Invalid data ingestion topic (%s), allowing it for now TODO" % ingest_data_topic)

        log.info('Setting up ingest topic for communication with a Dataset Agent: "%s"' % ingest_data_topic)
        self._subscriber = self.IngestSubscriber(xp_name="magnet.topic",
                                                 binding_key=ingest_data_topic,
                                                 process=self)
        yield self.register_life_cycle_object(self._subscriber) # move subscriber to active state


    @defer.inlineCallbacks
    def op_ingest(self, content, headers, msg):
        """
        Start the ingestion process by setting up necessary
        @TODO NO MORE MAGNET.TOPIC
        """
        log.info('<<<---@@@ Incoming perform_ingest request with "Perform Ingest" message')
        log.debug("...Content:\t" + str(content))

        if content.MessageType != PERFORM_INGEST_MSG_TYPE:
            raise IngestionError('Expected message type PerfromIngestRequest, received %s'
                                 % str(content), content.ResponseCodes.BAD_REQUEST)

        yield self._prepare_ingest(content)


        def _timeout():
            # trigger execution to continue below with a False result
            log.info("Timed out in op_perform_ingest")
            self._defer_ingest.callback(False)

        log.info('Setting up ingest timeout with value: %i' % content.ingest_service_timeout)
        timeoutcb = reactor.callLater(content.ingest_service_timeout, _timeout)

        log.info(
            'Notifying caller that ingest is ready by invoking op_ingest_ready() using routing key: "%s"' % content.reply_to)
        irmsg = yield self.mc.create_instance(INGESTION_READY_TYPE)
        irmsg.xp_name = "magnet.topic"
        irmsg.publish_topic = ingest_data_topic

        self.send(content.reply_to, operation='ingest_ready', content=irmsg)

        log.info("Yielding in op_perform_ingest for receive loop to complete")
        ingest_res = yield self._defer_ingest    # wait for other commands to finish the actual ingestion

        # common cleanup

        # reset ingestion deferred so we can use it again
        self._defer_ingest = defer.Deferred()

        # remove subscriber, deactivate it
        self._registered_life_cycle_objects.remove(self._subscriber)
        yield self._subscriber.terminate()
        self._subscriber = None

        if ingest_res:
            log.debug("Ingest succeeded, respond to original request")

            # we succeeded, cancel the timeout
            timeoutcb.cancel()

            # now reply ok to the original message
            yield self.reply_ok(msg)
        else:
            log.debug("Ingest failed, error back to original request")
            raise IngestionError("Ingestion failed", content.ResponseCodes.INTERNAL_SERVER_ERROR)

    @defer.inlineCallbacks
    def _notify_ingest(self, content):
        """
        Generate a notification/event that an ingest succeeded.
        """
        pub = yield self._notify_ingest_factory.build()

        # creates the event notification for us and sends it
        # @TODO: fields below
        yield pub.create_and_publish_event(origin=content.dataset_id,
                                           dataset_id=content.dataset_id,
                                           datasource_id="TODO",
                                           title="TODO",
                                           url="TODO")

    @defer.inlineCallbacks
    def op_recv_dataset(self, content, headers, msg):
        log.info("op_recv_dataset(%s)" % type(content))
        # this is NOT rpc

        if content.MessageType != CDM_DATASET_TYPE:
            raise IngestionError('Expected message type CDM Dataset Type, received %s'
                                 % str(content), content.ResponseCodes.BAD_REQUEST)

        #print '===== Content ==== \n', content

        #print '===== Dataset ======\n', self.dataset

        if self.dataset is None:
            raise IngestionError('Calling recv_dataset in an invalid state. No Dataset checked out to ingest.')

        if self.dataset.Repository.status is not self.dataset.Repository.UPTODATE:
            raise IngestionError('Calling recv_dataset in an invalid state. Dataset is already modified.')

        self.dataset.CreateUpdateBranch(content.MessageObject)

        group = self.dataset.root_group

        # Clear any bounded arrays which are empty. Create content field if it is not present
        for var in group.variables:
            if var.IsFieldSet('content'):
                content = var.content

                if len(content.bounded_arrays) > 0:
                    i = 0
                    while i < len(content.bounded_arrays):
                        ba = content.bounded_arrays[i]

                        if not ba.IsFieldSet('ndarray'):
                            del content.bounded_arrays[i]

                            continue
                        else:
                            i += 1
            else:
                var.content = resource_instance.CreateObject(array_structure_type)

        #print '===== Dataset Updated ======\n',self.dataset.Resource.PPrint()

        yield msg.ack()

    @defer.inlineCallbacks
    def op_recv_chunk(self, content, headers, msg):
        log.info("op_recv_chunk(%s)" % type(content))
        # this is NOT rpc
        if content.MessageType != SUPPLEMENT_MSG_TYPE:
            raise IngestionError('Expected message type SupplementMessageType, received %s'
                                 % str(content), content.ResponseCodes.BAD_REQUEST)
            #print '===== Content ==== \n', content

        #print '===== Dataset ======\n', self.dataset

        if self.dataset is None:
            raise IngestionError('Calling recv_chunk in an invalid state. No Dataset checked out to ingest.')

        if self.dataset.ResourceLifeCycleState is not self.dataset.UPDATE:
            raise IngestionError('Calling recv_chunk in an invalid state. Dataset is not on an update branch!')

        if content.dataset_id != self.dataset.ResourceIdentity:
            raise IngestionError('Calling recv_chunk with a dataset that does not match the received chunk!.')


        # Get the group out of the datset
        group = self.dataset.root_group

        # get the bounded array out of the message
        ba = content.bounded_array


        # Create a blobs message to send to the datastore with the ndarray
        blobs_msg = yield self.mc.create_instance(BLOBS_MESSAGE_TYPE)
        ndarray_element = content.Repository.index_hash.get(ba.ndarray.MyId)
        obj = content.Repository._wrap_message_object(ndarray_element._element)

        link = blobs_msg.blob_elements.add()
        link.SetLink(obj)

        # Put it to the datastore
        try:
            yield self.dsc.put_blobs(blobs_msg)
        except ReceivedError, re:
            log.error(re)
            raise IngestionError('Could not put blob in received chunk to the datastore.')

        # Now add the bounded array, but not the ndarray to the dataset in the ingestion service
        log.debug('Adding content to variable name: %s' % content.variable_name)
        try:
            var = group.FindVariableByName(content.variable_name)
        except gpb_wrapper.OOIObjectError, oe:
            log.error(str(oe))
            raise IngestionError('Expected variable name %s not found in the dataset' % (content.variable_name))

        ba_link = var.content.bounded_arrays.add()
        my_ba = ba_link.Repository.copy_object(ba, deep_copy=False)
        ba_link.SetLink(my_ba)

        yield msg.ack()

    @defer.inlineCallbacks
    def op_recv_done(self, content, headers, msg):
        log.info("op_recv_done(%s)" % type(content))
        if content.MessageType != DAQ_COMPLETE_MSG_TYPE:
            raise IngestionError('Expected message type Data Acquasition Complete Message Type, received %s'
                                 % str(content), content.ResponseCodes.BAD_REQUEST)

        if len(self.dataset.Repository.branches) != 2:

            raise IngestionError('The dataset is in a bad state - there should be two branches in the repository state on entering recv_done.', 500)


        self.dataset.Repository.commit('Ingest received complete notification.')

        merge_branch = self.dataset.Repository.current_branch_key()


        yield self.dataset.MergeWith(branchname=merge_branch, parent_branch='master')

        #Remove the head for the update!
        self.dataset.Repository.remove_branch(merge_branch)

        print self.dataset.Repository


        merge_root = self.dataset.Merge[0].root_group

        dimension_order = []

        for merge_var in merge_root.variables:

            print '\n\n\n\n\n\n'
            print merge_var.name
            print merge_var.shape.PPrint()

            # Add each dimension in reverse order so that the inside dimension is always in front... to determine the time aggregation dimension
            for merge_dim in reversed(merge_var.shape):

                if merge_dim not in dimension_order:
                    print 'adding dimension name: %s '% merge_dim.name

                    dimension_order.insert(0, merge_dim)

        print 'FINAL DIM ORDER'
        print [ dim.name for dim in dimension_order]


        merge_agg_dim = dimension_order[0]


        root = self.dataset.root_group

        agg_offset = 0
        try:
            agg_dim = root.FindDimensionByName(merge_agg_dim.name)
            agg_offset = agg_dim.length
            log.info('Aggregation offset from current dataset: %d' % agg_offset)

        except OOIObjectError, oe:
            log.debug('No Dimension found in current dataset:' + str(oe))

        try:
            string_time = merge_root.FindAttributeByName('ion_time_coverage_start')
            supplement_stime = calendar.timegm(time.strptime(string_time.GetValue(), '%Y-%m-%dT%H:%M:%SZ'))

        except OOIObjectError, oe:
            log.debug('No start time attribute found in dataset supplement!' + str(oe))
            raise IngestionError('No start time attribute found in dataset supplement!')


        try:
            string_time = root.FindAttributeByName('ion_time_coverage_end')
            current_etime = calendar.timegm(time.strptime(string_time.GetValue(), '%Y-%m-%dT%H:%M:%SZ'))

            if current_etime == supplement_stime:
                agg_offset -= 1
                log.info('Aggregation offset decremented by one - supplement overlaps: %d' % agg_offset)
            else:
                log.info('Aggregation offset unchanged - supplement does not overlap.')

        except OOIObjectError, oe:
            log.debug(oe)
            log.info('Aggregation offset unchanged - dataset has no ion_time_coverage_end.')


        for merge_var in merge_root.variables:
            var_name = merge_var.name


            if merge_agg_dim not in merge_var.shape:
                log.info('Nothing to merge on variable %s which does not share the aggregation dimension' % var_name)
                continue



            try:
                var = root.FindVariableByName(var_name)
            except OOIObjectError, oe:
                log.debug(oe)
                log.info('Variable %s does not yet exist in the dataset!' % var_name)

                v_link = root.variables.add()
                v_link.SetLink(merge_var)

                log.info('Copied Variable %s into the dataset!' % var_name)
                continue


            print 'MERGEING VAR %s' % var_name
            print var.content.PPrint()

            for merge_ba in merge_var.content.bounded_arrays:
                ba = var.Repository.copy_object(merge_ba, deep_copy=False)

                ba.bounds[0].origin += agg_offset

            log.info('Merged Variable %s into the dataset!' % var_name)


            print 'MERGEING Complete %s' % var_name
            print var.content.PPrint()

            
            



        # send notification we performed an ingest
        #yield self._notify_ingest(content)


        # this is NOT rpc
        yield msg.ack()

        # trigger the op_perform_ingest to complete!
        self._defer_ingest.callback(True)


class IngestionClient(ServiceClient):
    """
    Class for the client accessing the resource registry.
    """

    def __init__(self, proc=None, **kwargs):
        # Step 1: Delegate initialization to parent "ServiceClient"
        if not 'targetname' in kwargs:
            kwargs['targetname'] = "ingestion"
        ServiceClient.__init__(self, proc, **kwargs)

        # Step 2: Perform Initialization
        self.mc = MessageClient(proc=self.proc)

    #        self.rc = ResourceClient(proc=self.proc)


    @defer.inlineCallbacks
    def ingest(self, msg):
        """
        Start the ingest process by passing the Service a topic to communicate on, a
        routing key for intermediate replies (signaling that the ingest is ready), and
        a custom timeout for the ingest service (since it may take much longer than the
        default timeout to complete an ingest)
        @param msg, GPB 2002/1, a PerformIngestMessage
        @retval Result is an empty ION Message, reply_ok
        @GPB{Input,2002,1}
        """
        log.debug('-[]- Entered IngestionClient.perform_ingest()')
        # Ensure a Process instance exists to send messages FROM...
        #   ...if not, this will spawn a new default instance.
        yield self._check_init()

        ingest_service_timeout = msg.ingest_service_timeout

        # Invoke [op_]() on the target service 'dispatcher_svc' via RPC
        log.info("@@@--->>> Sending 'perform_ingest' RPC message to ingestion service")
        (content, headers, msg) = yield self.rpc_send('ingest', msg, timeout=ingest_service_timeout + 30)

        defer.returnValue(content)

    @defer.inlineCallbacks
    def create_dataset_topics(self, msg):
        yield self._check_init()
        (content, headers, msg) = yield self.rpc_send('create_dataset_topics', msg)
        defer.returnValue(content)

    @defer.inlineCallbacks
    def send_dataset(self, topic, msg):
        ''' For testing the service...'''
        yield self._check_init()
        yield self.proc.send(topic, operation='recv_dataset', content=msg)

    @defer.inlineCallbacks
    def send_chunk(self, topic, msg):
        ''' For testing the service...'''
        yield self._check_init()
        yield self.proc.send(topic, operation='recv_chunk', content=msg)

    @defer.inlineCallbacks
    def send_done(self, topic, msg):
        ''' For testing the service...'''
        yield self._check_init()
        yield self.proc.send(topic, operation='recv_done', content=msg)


# Spawn of the process using the module name
factory = ProcessFactory(IngestionService)
