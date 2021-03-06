#!/usr/bin/env python


"""
@file ion/core/data/index_store_service.py
@author Matt Rodriguez
@author David Stuebe
@brief Service which fronts the index store capability through the messaging to a single back end.
"""

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)
from twisted.internet import defer

from ion.core.process.process import ProcessFactory
from ion.core.process.service_process import ServiceProcess, ServiceClient
from ion.core.object import object_utils

from ion.core.data.store import Query

from ion.core.data.store import IIndexStore, IndexStore, IndexStoreError
from zope.interface import implements

from ion.core import ioninit
CONF = ioninit.config(__name__)



QUERY_ATTRIBUTES_TYPE = object_utils.create_type_identifier(object_id=17, version=1)
ROW_TYPE = object_utils.create_type_identifier(object_id=18, version=1)
ROWS_TYPE = object_utils.create_type_identifier(object_id=19, version=1)
INDEXED_ATTRIBUTES_TYPE = object_utils.create_type_identifier(object_id=20, version=1)
ROW_INDEX_UPDATE_TYPE = object_utils.create_type_identifier(object_id=21, version=1)


class IndexStoreServiceException(Exception):
    """
    Exceptions that originate in the IndexStoreService class
    """

class IndexStoreService(ServiceProcess):
    """
    @brief IndexStoreService

    This is not a ION service. It is part of a test harness to provide a pure, in memory backend for the data store
    and the association service

    TODO, this class does not catch any exceptions from the business logic class. 
    """

    # Declaration of service
    declare = ServiceProcess.service_declare(name='index_store_service', version='0.1.0', dependencies=[])

    def __init__(self, *args, **kwargs):
        # Service class initializer. Basic config, but no yields allowed.
        ServiceProcess.__init__(self, *args, **kwargs)

        log.info(self.spawn_args)
        self.indices = self.spawn_args.get('indices',  [])
        log.info(self.indices)
        
    #@defer.inlineCallbacks
    def slc_activate(self, *args):
        """
        Activation can be automatic when the process is spawned or triggered by
        a message from the client.
        
        First, default to bootstrapping from the spawn args. Create all resources
        by describing the cluster!
        
        Second, add hooks to override the spawn args and take the storage resource
        reference from a message in op_activate - connecting to an already active
        system!
        
        """
        IndexStore.kvs={}
        IndexStore.indices={}
        self._indexed_store = IndexStore(indices=self.indices)

        log.info("Created Index Store Service")
        
        
        

    @defer.inlineCallbacks
    def op_query(self, request, headers, msg):
        """
        @Note The goal is to return a dictionary of keys and resourceids.
        @retval return a cassandra_rows type. The key attribute will be set and each row will contain one column 
        with the name value.
        """
        log.debug("In op_query: request %s" % request)

        query_predicates = Query()    
        for attr in request.attrs:
            if attr.predicate_type == Query.EQ:
                query_predicates.add_predicate_eq(attr.attribute_name, attr.attribute_value)
            elif attr.predicate_type == Query.GT:
                query_predicates.add_predicate_gt(attr.attribute_name, attr.attribute_value)
            else:
                raise IndexStoreServiceException("Unhandled predicate type: %s " % (attr.predicate_type,))
                
        results = yield self._indexed_store.query(query_predicates)
        #Now we have to put these back into a response
        response = yield self.message_client.create_instance(ROWS_TYPE)
        
    
        #The GPB buffer object represents cassandra rows, we could probably get away with just making a dictionary like
        #object, since that's what query returns.
        for key,row in results.items():
            r = response.rows.add()
            r.key = key


            r.value = row.pop('value')

            for name, val in row.items():
                col = r.cols.add()
                col.column_name = name
                col.column_value = val
        
        log.debug("op_query Result %s" % response)

        yield self.reply_ok(msg,response)
            
    @defer.inlineCallbacks
    def op_put(self, request, headers, msg):
        """
        @note, puts a row into the Cassandra cluster. 
        @retval does not return anything
        """
        key = request.key
        value = request.value
        index_attrs = {}
        for col in request.cols:
            index_attrs[col.column_name] = col.column_value
        yield self._indexed_store.put(key=key,value=value,index_attributes=index_attrs)

        yield self.reply_ok(msg)
        

    @defer.inlineCallbacks
    def op_update_index(self, request, headers, msg):
        key = request.key
        index_attrs = {}
        for col in request.cols:
            index_attrs[col.column_name] = col.column_value
        yield self._indexed_store.update_index(key,index_attrs)
        log.info("In op_update_index")
        yield self.reply_ok(msg)

    @defer.inlineCallbacks
    def op_get(self, request, headers, msg):
        """
        @note Gets a row from the Cassandra cluster
        If the row does not exist then leave the value field in the CassandraIndexedRow empty.
        @param request is a CassandraRow message object
        @retval Returns a CassandraRow message in the response   
        """

        value = yield self._indexed_store.get(request.key)
        response = yield self.message_client.create_instance(ROW_TYPE)
        response.key = request.key
        
        if value is not None:
            response.value = value

        # Consider using raise with a not found response?
        yield self.reply_ok(msg, response)
         
    @defer.inlineCallbacks
    def op_remove(self, request, headers, msg): 
        """
        @note removes a row
        @param request is a CassandraRow message object
        @retval does not return anything
        """     

        yield self._indexed_store.remove(request.key)
        yield self.reply_ok(msg)
        
    @defer.inlineCallbacks
    def op_has_key(self, request, headers, msg):
        """
        @note sees if key exists in the cluster
        @request is a CassandraRow message object
        @retval return a string that is "True" or "False" in a CassandraRow message
        """
        key_exists = yield self._indexed_store.has_key(request.key)
        log.info("key_exists: " + str(key_exists))
        response = yield self.message_client.create_instance(ROW_TYPE)
        response.value = str(int(key_exists))
        yield self.reply_ok(msg, response)
        
    @defer.inlineCallbacks
    def op_get_query_attributes(self, request, headers, msg):
        """
        @note gets the names of the columns that are indexed in the column family
        @retval returns the names of the columns in a CassandraRow message
        """      
        column_list = yield self._indexed_store.get_query_attributes()
        response = yield self.message_client.create_instance(INDEXED_ATTRIBUTES_TYPE)
        log.info(column_list)
        response.attributes.extend(column_list)

        log.info("replying for get_query_attributes")         
        yield self.reply_ok(msg, response)
        
# Spawn of the process using the module name
factory = ProcessFactory(IndexStoreService)


class IndexStoreServiceClient(ServiceClient):
    """
    This interface will change, because we have to define the ION resources. We probably want
    convenience methods to query by name, type, etc...
    
    TODO have this implement the Indexstore interface
    """
    implements(IIndexStore)
    
    def __init__(self, proc=None, **kwargs):
        if not 'targetname' in kwargs:
            kwargs['targetname'] = 'index_store_service'
        ServiceClient.__init__(self, proc, **kwargs)
        
        self.mc = proc.message_client
    
      
    @defer.inlineCallbacks
    def query(self, query_predicates):
        log.info("Called Index Store Service client: Query")
        
        request = yield self.mc.create_instance(QUERY_ATTRIBUTES_TYPE)

        for attr_key,attr_value,pred_type in query_predicates.get_predicates():
            attr = request.attrs.add()                
            attr.attribute_name = str(attr_key)
            attr.attribute_value = str(attr_value)
            attr.predicate_type = str(pred_type)

        (result, headers, msg) = yield self.rpc_send('query', request)


        results ={}
        for row in result.rows:

            cols = {'value':row.value}

            for col in row.cols:
                cols[col.column_name] = col.column_value

            results[row.key] = cols

        defer.returnValue(results)
        
    @defer.inlineCallbacks
    def put(self, key, value, index_attributes=None):
        log.info("Called Index Store Service client: put")
        
        if index_attributes is None:
            index_attributes = {}
        
        row = yield self.mc.create_instance(ROW_TYPE)
        row.key = key
        row.value = value
        
        for attr_key,attr_value in index_attributes.items():
            col = row.cols.add()
            col.column_name = attr_key
            col.column_value = str(attr_value)
        
        (content, headers, msg) = yield self.rpc_send('put', row)
        

        defer.returnValue(content)

    @defer.inlineCallbacks
    def update_index(self, key, index_attributes):
        """
        use
        """

        row = yield self.mc.create_instance(ROW_INDEX_UPDATE_TYPE)
        row.key = key

        for attr_key,attr_value in index_attributes.items():

            if attr_key == 'value':
                raise IndexStoreError('Can not update the value column!')

            col = row.cols.add()
            col.column_name = attr_key
            col.column_value = str(attr_value)

        (content, headers, msg) = yield self.rpc_send('update_index', row)


        defer.returnValue(None)



    @defer.inlineCallbacks
    def get(self, key):
        log.info("Called Index Store Service client: get")
        row = yield self.mc.create_instance(ROW_TYPE)
        row.key = key
          
        (result, headers, msg) = yield self.rpc_send('get',row)

        if not result.value is '':
            defer.returnValue(result.value)
        else:
            defer.returnValue(None)
        
    @defer.inlineCallbacks
    def remove(self, key):
        log.info("Called Index Store Service client: remove")
        row = yield self.mc.create_instance(ROW_TYPE)
        row.key = key
          
        (content, headers, msg) = yield self.rpc_send('remove', row)
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def has_key(self, key):
        log.info("Called Index Store Service client: has_key")    
        row = yield self.mc.create_instance(ROW_TYPE)
        row.key = key
        (result, headers, msg) = yield self.rpc_send('has_key', row)
        ret = bool(int(result.value))
        log.info("%s" % (ret,))
        defer.returnValue(ret)
        
    @defer.inlineCallbacks
    def get_query_attributes(self):

        log.info("Called Index Store Service client: get_query_attributes")
        
        (result, headers, msg) = yield self.rpc_send('get_query_attributes','')

        defer.returnValue(result.attributes)
        
        
