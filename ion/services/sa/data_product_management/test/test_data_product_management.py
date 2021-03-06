#!/usr/bin/env python

"""
@file ion/services/sa/test/test_data_product_management.py
@test ion.services.sa.data_product_management
@author
"""

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)
from twisted.internet import defer

from ion.core.process.process import Process
from ion.services.sa.data_product_management.data_product_management import DataProductManagementServiceClient
from ion.test.iontest import IonTestCase


class DataProductManagementTest(IonTestCase):
    """
    Testing data product management service
    """

    @defer.inlineCallbacks
    def setUp(self):
        yield self._start_container()

        services = [
            {
                'name':'dataprodmgmt',
                'module':'ion.services.sa.data_product_management.data_product_management',
                'class':'DataProductManagementService'
            },
            {
                'name':'dataacqmgmt',
                'module':'ion.services.sa.data_acquisition_management.data_acquisition_management',
                'class':'DataAcquisitionManagementService'
            }
        ]

        log.debug('DataProductManagementTest.setUp(): spawning processes')
        sup = yield self._spawn_processes(services)
        log.debug('DataProductManagementTest.setUp(): spawned processes')
        self.sup = sup
        self.dpmsc = DataProductManagementServiceClient(proc=sup)
        self._proc = Process()


    @defer.inlineCallbacks
    def tearDown(self):
        yield self._shutdown_processes()
        yield self._stop_container()


    @defer.inlineCallbacks
    def test_define_data_product(self):
        """
        Accepts a dictionary containing metadata about a data product.
        Updates are made to the registries.
        """

        log.info("test_define_data_product Now testing: Create sample data product")

        # create a data product w/o a data producer
        result = yield self.dpmsc.define_data_product(ParameterDictionary={'title':'CTD data',
                                                                           'summary':'Data from Seabird instrument',
                                                                           'keywords':'salinity, temperature'})
        if isinstance(result, dict) != True:
            self.fail("response is not a dictionary")
        log.debug("define_data_product returned " + str(result))

        # create a data product with a data producer
        result = yield self.dpmsc.define_data_product(ParameterDictionary={'title':'ADCP data',
                                                                           'summary':'Data from Workhorse instrument',
                                                                           'keywords':'current',
                                                                           'data_producer':{'data_producer_name':'InstrumentAgent_123'}})
        if isinstance(result, dict) != True:
            self.fail("response is not a dictionary")
        log.debug("define_data_product returned " + str(result))

        log.info("define_data_product Finished testing: Create sample data product")


    @defer.inlineCallbacks
    def test_get_data_product_detail(self):
        """
        Accepts an OOI ID for a data product.
        returns the data product.
        """

        log.info("test_get_data_product_detail Now testing: get a data product")

        # create a data product w/o a data producer
        result = yield self.dpmsc.define_data_product(ParameterDictionary={'title':'CTD data',
                                                                           'summary':'Data from Seabird instrument',
                                                                           'keywords':'salinity, temperature'})
        if isinstance(result, dict) != True:
            self.fail("response is not a dictionary")
        log.debug("define_data_product returned " + str(result))
        result = yield self.dpmsc.get_data_product_detail(data_product_ooi_id=result['data_product_ooi_id'])
        if isinstance(result, dict) != True:
            self.fail("response is not a dictionary")
        log.debug("get_data_product_detail returned " + str(result))

        # create a data product with a data producer
        result = yield self.dpmsc.define_data_product(ParameterDictionary={'title':'ADCP data',
                                                                           'summary':'Data from Workhorse instrument',
                                                                           'keywords':'current',
                                                                           'data_producer':{'data_producer_name':'InstrumentAgent_123'}})
        if isinstance(result, dict) != True:
            self.fail("response is not a dictionary")
        log.debug("define_data_product returned " + str(result))
        result = yield self.dpmsc.get_data_product_detail(data_product_ooi_id=result['data_product_ooi_id'])
        if isinstance(result, dict) != True:
            self.fail("response is not a dictionary")
        log.debug("get_data_product_detail returned " + str(result))
        
        # get a data product that doesn't exist
        result = yield self.dpmsc.get_data_product_detail(data_product_ooi_id='72B744B3-9CE0-476C-93B3-66AF114BOGUS')
        if isinstance(result, dict) != True:
            self.fail("response is not a dictionary")
        log.debug("get_data_product_detail returned " + str(result))

        log.info("get_data_product_detail Finished testing: get a data product")


    @defer.inlineCallbacks
    def test_find_data_products(self):
        """
        Accepts a filter.
        returns data products that match.
        """

        log.info("test_find_data_product Now testing: find data products")
        # create a data product w/o a data producer
        result = yield self.dpmsc.define_data_product(ParameterDictionary={'title':'CTD1 data',
                                                                           'summary':'Data from Seabird instrument',
                                                                           'keywords':'salinity, temperature'})
        result = yield self.dpmsc.define_data_product(ParameterDictionary={'title':'CTD2 data',
                                                                           'summary':'Data from Seabird instrument',
                                                                           'keywords':'salinity, temperature'})
        # create a data products with a data producer
        result = yield self.dpmsc.define_data_product(ParameterDictionary={'title':'ADCP data',
                                                                           'summary':'Data from Workhorse instrument',
                                                                           'keywords':'current',
                                                                           'data_producer':{'data_producer_name':'InstrumentAgent_123'}})
        result = yield self.dpmsc.find_data_products(filter={'summary':'Data from Seabird instrument'})
        log.debug("find_product returned " + str(result))

        log.info("find_data_product_detail Finished testing: find a data product")

   
    @defer.inlineCallbacks
    def test_set_data_product_detail(self):
        """
        Accepts dictionary of fields for a data product.
        returns the data product detail.
        """

        log.info("test_set_data_product_detail Now testing: set a data product")

        # create a data product with a data producer
        define_result = yield self.dpmsc.define_data_product(ParameterDictionary={'title':'CTD data',
                                                                                  'summary':'Data from Seabird instrument',
                                                                                  'keywords':'salinity, temperature'})
        if isinstance(define_result, dict) != True:
            self.fail("response is not a dictionary")
        log.debug("define_data_product returned " + str(define_result))
        
        # get the data product back from the service
        result = yield self.dpmsc.get_data_product_detail(data_product_ooi_id=define_result['data_product_ooi_id'])
        if isinstance(result, dict) != True:
            self.fail("response is not a dictionary")
        log.debug("get_data_product_detail returned " + str(result))
        
        # change some of the data product fields and set them in the service
        product = result['product']
        product['title'] = "CTD3 data"
        result = yield self.dpmsc.set_data_product_detail(ParameterDictionary=product)
        result = yield self.dpmsc.get_data_product_detail(data_product_ooi_id=define_result['data_product_ooi_id'])
        if isinstance(result, dict) != True:
            self.fail("response is not a dictionary")
        log.debug("get_data_product_detail returned " + str(result))
            
        # add a data producer to the data product
        product['data_producer'] = {'data_producer_name':'InstrumentAgent_123'}
        result = yield self.dpmsc.set_data_product_detail(ParameterDictionary=product)
        result = yield self.dpmsc.get_data_product_detail(data_product_ooi_id=define_result['data_product_ooi_id'])
        if isinstance(result, dict) != True:
            self.fail("response is not a dictionary")
        log.debug("get_data_product_detail returned " + str(result))
        


  
  