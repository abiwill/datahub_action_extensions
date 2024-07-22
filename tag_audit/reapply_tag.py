import json
import logging
import re
import requests
import time
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from datahub_actions.action.action import Action
from datahub_actions.event.event_envelope import EventEnvelope
from datahub_actions.event.event_registry import EntityChangeEvent
from datahub_actions.pipeline.pipeline_context import PipelineContext
from datahub.configuration.common import ConfigModel

from string import Template
from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport

from elasticsearch import Elasticsearch
from urllib.parse import urlparse

import pkg_resources


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)



class TagReApplicationConfig(ConfigModel):
    """
    Configuration model for tag reapplication

    Attributes:
        enabled (bool) : Indicates wether tag reapplication is enabled or not. Default is True
        tag_prefixes (List[str]) : List of tag prefixes to be re-applied

    Note :
        Tag reapplication is enabled by default and it allows tag matching the prefix to be reapplied. 
        As soon as a matched tag is removed, the tag is reapplied and an audit doc is ingested in elasticsearch.

    Example :
        config = TagReApplicatoinConfig(enabled = True, tag_prefixes = ['tag1', 'tag2'])
    """

    enabled : bool = Field(True, description="Indicates wether tag reapplication is enabled or not", example=True)
    tag_prefixes : List[str] = Field([], description="List of tag prefixes to be re-applied", example=['tag1', 'tag2'])
    es: Optional[dict] = None
    gms: Optional[dict] = None


class TagReApplicationAction(Action):
    """action to reapply tag based on prefix matched"""

    def __init__(self, config: TagReApplicationConfig, ctx: PipelineContext):
        self.config : TagReApplicationConfig = config
        self.ctx : PipelineContext = ctx
        # send the gql request
        # Select your transport with a defined url endpoint
        url_frag = "/api/graphql"
        # self.gms_url = self.config.gms['url'] + url_frag
        self.gms_url = config.gms['url'] + url_frag
        transport = AIOHTTPTransport(url=self.gms_url, headers={"Authorization": f"Bearer {config.gms['token']}"})
        
        # Create a GraphQL client using the defined transport
        self.client = Client(transport=transport, fetch_schema_from_transport=False)

    @classmethod
    def create(cls, config_dict, ctx) -> "TagReApplicationAction":
        config = TagReApplicationConfig.parse_obj(config_dict)
        logger.info(f"TagReApplicationAction created with config: {config}")
        return cls(config, ctx)


    def name(self) -> str:
        return "TagReApplicationAction"
    
    def load_data(self, filename: str):
        file_path = pkg_resources.resource_filename(__name__, f'data/{filename}')
        with open(file_path, 'r') as file:
            if filename.endswith('.json'):
                return file.read()
            elif filename.endswith('.gql'):
                return file.read()
            else:
                raise ValueError('Unsupported file type')
    
    def getDatasetUrn(self, entityurn):
        """return dataset urn from entity urn"""
        try:
            logger.info(f"Get dataset urn called: {entityurn}")
            datasetPattern = r"urn:li:dataset:\(urn:li:dataPlatform:[^,]+,[^,]+,[^,]+\)"
            datasetUrn = re.search(datasetPattern, entityurn).group()
            return datasetUrn
        except Exception as e:
            logger.error(f"Error in getDatasetUrn: {e}")
            raise


    
    def getDomainFromDataset(self, dataseturn):
        """get domain from dataset urn"""
        try:
            # query file
            # with open('getDomainFromDataset.gql') as f:
            #     get_domain_query = f.read()

            get_domain_query = self.load_data('getDomainFromDataset.gql')
            
    
            input_var = { "urn": dataseturn }
            query = gql(get_domain_query)
    
            # Execute the query on the transport
            logger.info(f"Executing get domain query with input vars {input_var} on gms url : {self.gms_url} with dataset urn : {dataseturn}")
            response = self.client.execute(query, variable_values=input_var)
    
            domainUrn = response['dataset']['domain']['domain']['urn']
            domainName = response['dataset']['domain']['domain']['properties']['name']
    
            return {'domainUrn': domainUrn, 'domainName': domainName}
        except Exception as e:
            logger.error(f"Error in getDomainFromDataset: {e}")
            raise

    
    def sendToES(self, auditdoc) -> None:
        """send audit to ES"""

        url = self.config.es['url']
        username = self.config.es['username']
        password = self.config.es['password']
        max_retries = self.config.es['max_retries']
        retry_delay = self.config.es['retry_delay']
        index = self.config.es['index']

        logger.info(f"Sending audit doc to ES: {auditdoc}")

        # check the url scheme and if usernam, password is provided
        parsed_url = urlparse(url)
        use_ssl = parsed_url.scheme == 'https'

        if username and password:
            http_auth = (username, password)
        else:
            http_auth = None

        logger.info(f"Trying to connect to ES: {url} with http_auth: {http_auth} , use_ssl: {use_ssl}, max_retries: {max_retries}, retry_delay: {retry_delay}")

        esClient = Elasticsearch(
            hosts=[url], 
            http_auth=http_auth, 
            verify_certs=use_ssl,
            # sniff_on_start=True,
            # sniff_on_connection_fail=True,
            # sniff_timeout=60                     
            )
        
        # send the doc to ES
        for attempt in range(max_retries):
            try:
                resp = esClient.index(index=index, document=auditdoc)
                logger.info(f"Sent audit doc to ES: {auditdoc}, Response:  {resp}")
                return resp
            except Exception as e:
                logger.error(f"Attempt {attempt} failed to send audit doc to ES: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise

    
    def reapplyTag(self, tagUrn: str, entityUrn: str, fieldPath: str, entityType: str) -> None:
        """reapply tag"""
        try:
            assert self.ctx.graph is not None
            # datasetPattern = r"urn:li:dataset:\(urn:li:dataPlatform:[^,]+,[^,]+,[^,]+\)"
            datasetUrn = self.getDatasetUrn(entityUrn)
    
            # # query file
            # with open('batchAddTags.gql') as f:
            #     add_tag_query = f.read()
    
            # # open the input var template file and substitute the values
            # with open('batchAddTag_Input.json') as f:
            #     input_file = f.read()

            add_tag_query = self.load_data('batchAddTags.gql')
            input_file = self.load_data('batchAddTag_Input.json')
    
            template = Template(input_file)
    
            # substitute the values
            values = {
                "tagUrn": tagUrn,
                "resourceUrn": datasetUrn,
                "fieldPath": fieldPath
            }

    
            input_var = template.substitute(values) if entityType != "dataset" else json.dumps({"input": {"tagUrns": tagUrn, "resources": [{ "resourceUrn": datasetUrn}]}})
            query = gql(add_tag_query)
    
            # Execute the query on the transport
            logger.info(f"Executing query applytag query with input vars {input_var} on gms url : {self.gms_url}")
            response = self.client.execute(query, variable_values=json.loads(input_var))
    
            logger.info(f"Tag {tagUrn} reapplied on {entityUrn} {fieldPath}")
        except Exception as e:
            logger.error(f"Error in reapplyTag: {e}")
            raise


    def matchTag(self, event: EventEnvelope) -> None:
        """return a tag urn to reapply"""
        try:
            logger.info(f"{event}")
            if event.event_type == "EntityChangeEvent_v1" and event.event.operation == "REMOVE" and event.event.category == "TAG":
                assert isinstance(event.event, EntityChangeEvent)
                assert self.ctx.graph is not None
                semantic_event = json.loads(event.event.as_json())
                category = semantic_event['category']
                operation = semantic_event['operation']
                tagUrn = semantic_event['parameters']['tagUrn']
                entityUrn = semantic_event['entityUrn']
                datasetUrn = self.getDatasetUrn(entityUrn)
                entityType = semantic_event['entityType']
                fieldPath =  semantic_event['parameters']['fieldPath'] if entityType != "dataset" else None
                actor = semantic_event['auditStamp']['actor']
                time = datetime.fromtimestamp(semantic_event['auditStamp']['time']/1000)
                es_time = time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                domainValues = self.getDomainFromDataset(datasetUrn)
                domainUrn = domainValues['domainUrn']
                domainName = domainValues['domainName']
    
                logger.info(f"GotEntityChangeEvent: {category} {operation} {tagUrn} {entityUrn} {entityType} {fieldPath} {actor} {es_time} {time}")
    
                # send audit to ES
                audit_doc = {
                    "category": category,
                    "operation": operation,
                    "tagUrn": tagUrn,
                    "entityUrn": entityUrn,
                    "datasetUrn": datasetUrn,
                    "entityType": entityType,
                    "fieldPath": fieldPath,
                    "actor": actor,
                    "domainUrn": domainUrn,
                    "domainName": domainName,
                    "time": es_time
                }
                self.sendToES(audit_doc)
    
                for prefix_regex in self.config.tag_prefixes:
                    logger.info(f"prefix_regex: {prefix_regex}")
                    if re.search(prefix_regex, tagUrn):
                        logger.info(f"Tag {tagUrn} matched with prefix {self.config.tag_prefixes}")
                        self.reapplyTag(tagUrn, entityUrn, fieldPath, entityType)
                    else:
                        logger.warn(f"Tag {tagUrn} on dataset {entityUrn} did not match with prefix {prefix_regex}")

            else:
                logger.warn(f"Event {event} is not an EntityChangeEvent_v1 or not a tag removal event")
        except Exception as e:
            logger.error(f"Error in matchTag: {e}")
            raise


    def act(self, event: EventEnvelope) -> None:
        """reapply tag based on prefix matched"""
        self.matchTag(event)


    def close(self) -> None:
        return super().close()
