#!/usr/bin/env python

"""
@file ion/services/coi/resource_registry_beta/resource_client.py
@author David Stuebe
@brief base classes for resrouce client
"""

from twisted.internet import defer, reactor
from twisted.python import failure
from zope.interface import implements, Interface

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)

from ion.core import ioninit
from ion.core.exception import ReceivedError
import ion.util.procutils as pu
from ion.util.state_object import BasicLifecycleObject
from ion.core.messaging.ion_reply_codes import ResponseCodes
from ion.core.process import process
from ion.core.object import workbench

from ion.services.coi.resource_registry_beta.resource_registry import ResourceRegistryClient

from net.ooici.core.type import type_pb2
from net.ooici.resource import resource_pb2


CONF = ioninit.config(__name__)


class ResourceClient(object):
    """
    This is the base class for a resource client. It is a factory for resource
    instances. The api for working with a resource is in the instance. The client
    helps create and manage resources.
    """
    def __init__(self, proc=None, datastore_service='datastore'):
        """
        Initializes a process client
        @param proc a IProcess instance as originator of messages
        @param datastore the name of the datastore service with which you wish to
        interact
        @param registy the name of the registry services with which you wish to
        interact
        """
        if not proc:
            proc = process.Process()
        
        if not hasattr(proc, 'op_fetch_linked_objects'):
            setattr(proc, 'op_fetch_linked_objects', proc.workbench.op_fetch_linked_objects)
                        
        self.proc = proc
        
        self.datastore_service = datastore_service
                
        # The resource client is backed by a process workbench.
        self.workbench = self.proc.workbench        
        
        # What about the name of the index services to use?
        
        self.registry_client = ResourceRegistryClient(proc=self.proc)
        

    @defer.inlineCallbacks
    def _check_init(self):
        """
        Called in client methods to ensure that there exists a spawned process
        to send messages from
        """
        if not self.proc.is_spawned():
            yield self.proc.spawn()
        
        assert isinstance(self.workbench, workbench.WorkBench), \
        'Process workbench is not initialized'


    @defer.inlineCallbacks
    def create_type_identifier(self, package='', protofile='', cls=''):
        """
        Currently not a deferred method but it will be!
        """
        yield self._check_init()
            
        repo, type_id = self.workbench.init_repository(rootclass=type_pb2.GPBType)
            
        type_id.protofile = protofile
        type_id.package = package
        type_id.cls = cls
            
        defer.returnValue(type_id)

    
    @defer.inlineCallbacks
    def create_resource_instance(self, type_id, name, description=''):
        """
        A Factory Method for Resrouce Instance Objects
        Ask the resource registry to create the instance!
        """
        yield self._check_init()
        
        # Use the registry client to make a new resource        
        res_id = yield self.registry_client.register_resource_instance(type_id)
            
        response, exception = yield self.workbench.pull(self.datastore_service, res_id)
        assert response == self.proc.ION_SUCCESS, 'Push to datastore failed!'
        
        repo = self.workbench.get_repository(res_id)
        
        self.workbench.set_repository_nickname(res_id, name)
            
        # Get the default branch and set the name and description
        res_head = repo.checkout('master')
            
        res_head.name = name
        res_head.description = description
        
        repo.commit('set resource name and description')
        
        response, exception = yield self.workbench.push(self.datastore_service, name)
        assert response == self.proc.ION_SUCCESS, 'Push to datastore failed!'
        
        
        # Create a resource instance to return
        resource = ResourceInstance(repository=repo, workbench=self.workbench, datastore_service=self.datastore_service)

        defer.returnValue(resource)
        
    @defer.inlineCallbacks
    def retrieve_resource_instance(self, resource_id):
        """
        A factory method for resource instances which are already in the data store
        """
        yield self._check_init()
        
        # Pull the repository
        response, exception = yield self.workbench.pull(self.datastore_service, resource_id)
        assert response == self.proc.ION_SUCCESS, 'Push to datastore failed!'
        
        # Get the repository
        repo = self.workbench.get_repository(resource_id)
                    
        # Get the default branch and set the nickname
        res_head = repo.checkout('master')
            
        self.workbench.set_repository_nickname(resource_id, res_head.name)
        
        # Create a resource instance to return
        resource = ResourceInstance(repository=repo, workbench=self.workbench, datastore_service=self.datastore_service)
            
        defer.returnValue(resource)



    @defer.inlineCallbacks
    def find_resource(self, **kwargs):
        """
        Use the index to find resource instances that match a set of constraints
        For R1 the constraints that may be used are very limited
        """
        yield self._check_init()
            
        raise NotImplementedError, "Interface Method Not Implemented"
    
class ResourceInstance(object):
    """
    The instance is the vehicle through which the developer interacts with a
    particular resource. It hides the git semantics of the data store and deals
    with resource specific properties.
    """
    
    NEW='New'
    ACTIVE='Active'
    INACTIVE='Inactive'
    COMMISSIONED='Commissioned'
    DECOMMISSIONED='Decommissioned'
    RETIRED='Retired'
    DEVELOPED='Developed'
    
    def __init__(self, repository, workbench, datastore_service):
        """
        Resource Instance objects are created by the resource client factory methods
        """
        
        self.repository = repository
        
        self.workbench = workbench
        
        self.datastore_service = datastore_service
        
        self.resource = self.repository.checkout('master')    
    
    @defer.inlineCallbacks
    def read_resource(self, version='master'):
        """
        Read the current state of the resource - returns the head object for a structure
        At present getting the instance returns the entire resource + history!
        """
        # Checkout may become a deferred method or this may require interaction with the datastore
        self.resource = self.repository.checkout(version)
        res_obj = self.resource.resource_object
        defer.returnValue(res_obj)
        
    @defer.inlineCallbacks
    def write_resource(self, comment=None):
        """
        Write the current state of the resource to the data store- returns OK
        """
        if not comment:
            comment = 'Resource client default commit message'
        self.repository.commit(comment=comment)
        
        response, exception = yield self.workbench.push(self.datastore_service, self.name)
        assert response == self.proc.ION_SUCCESS, 'Push to datastore failed!'
        
#    def save_resource(self, comment=None):
#        """
#        Locally commit the current state of this resource - potentially to save process state
#        """
        
    def version_resource(self):
        """
        Create a new version of this resource - creates a new branch in the objects repository
        This is purely local until the next push!
        """
        
        branch_key = self.repository.branch()
        return branch_key
        
    @defer.inlineCallbacks
    def load_resource(self, version, commit_id=None):
        """
        Load a particular (previous) version of this resource
        """
        self.resource = self.repository.checkout(branch=version, commit_id=commit_id)
        res_obj = self.resource.resource_object
        defer.returnValue(res_obj)
        
    @property
    def identity(self):
        """
        Return the resource identity
        """
        return self.resource.identity
    
    def _set_life_cycle_state(self, state):
        """
        Set the Life Cycel State of the resource
        @param state is a resource life cycle state class variable defined in
        the ResourceInstance class.
        """
        # Using IS for comparison - I think this is better than the usual ==
        # Want to force the use of the self.XXXX as the argument!
        if state == self.NEW:        
            self.resource.lcs = resource_pb2.New
        elif state == self.ACTIVE:
            self.resource.lcs = resource_pb2.Active
        elif state == self.INACTIVE:
            self.resource.lcs = resource_pb2.Inactive
        elif state == self.COMMISSIONED:
            self.reource.lcs = resource_pb2.Commissioned
        elif state == self.DECOMMISSIONED:
            self.reource.lcs = resource_pb2.Decommissioned
        elif state == self.RETIRED:
            self.reource.lcs = resource_pb2.Retired
        elif state == self.DEVELOPED:
            self.reource.lcs = resource_pb2.Developed
        else:
            raise Exception('''Invalid argument value state: %s. State must be 
                one of the class variables defined in Resource Instance''' % str(state))
        
    def _get_life_cycle_state(self):
        """
        Get the life cycle state of the resource
        """
        state = None
        if self.resource.lcs == resource_pb2.New:
            state = self.NEW    
        
        elif self.resource.lcs == resource_pb2.Active:
            state = self.ACTIVE
            
        elif self.resource.lcs == resource_pb2.Inactive:
            state = self.INACTIVE
            
        elif self.reource.lcs == resource_pb2.Commissioned:
            state = self.COMMISSIONED
            
        elif self.reource.lcs == resource_pb2.Decommissioned:
            state = self.DECOMMISSIONED
            
        elif self.reource.lcs == resource_pb2.Retired:
            state = self.RETIRED
            
        elif self.reource.lcs == resource_pb2.Developed:
            state = self.DEVELOPED
        
        return state
        
    life_cycle_state = property(_get_life_cycle_state, _set_life_cycle_state)
    
    def _set_resource_name(self, name):
        """
        Set the name of the resource object
        """
        self.resource.name = name
        
    def _get_resource_name(self):
        """
        """
        return self.resource.name
    
    name = property(_get_resource_name, _set_resource_name)
    
    def _set_resource_description(self, description):
        """
        """
        self.resource.description = description
        
    def _get_resource_description(self):
        """
        """
        return self.resource.description 
        
    
    description = property(_get_resource_description, _set_resource_description)
    
