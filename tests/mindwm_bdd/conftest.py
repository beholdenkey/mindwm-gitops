import allure
import logging
import pytest
import re
import pprint
import kubetest
from kubetest.client import TestClient
from kubernetes import client
from kubetest.plugin import clusterinfo
from kubetest.objects.namespace import Namespace
from pytest_bdd import scenarios, scenario, given, when, then, parsers
import mindwm_crd
import re
import os
import utils
from typing import List
from messages import DataTable
from kubetest import utils as kubetest_utils
from kubetest import condition
import kubernetes.client.exceptions
import json
import requests
import time
from opentelemetry.proto.trace.v1 import trace_pb2
from google.protobuf.json_format import ParseDict
import nats
from nats.errors import ConnectionClosedError, TimeoutError, NoServersError
from functools import wraps
import inspect
import nats_reader
from queue import Empty
from neo4j import GraphDatabase
import uuid
import functools
import asyncio
from api_loki import pod_logs_should_contain_regex, pod_logs_should_not_contain_regex

from git_utils import git_clone
from tmux import create_tmux_session, send_command_to_pane, vertically_split_window, tmux_session_exists

nats_messages = []

# configure allure logging
class AllureLoggingHandler(logging.Handler):
    def log(self, message):
        with allure.step('Log {}'.format(message)):
	        pass

    def emit(self, record):
        self.log("({}) {}".format(record.levelname, record.getMessage()))

class AllureCatchLogs:
    def __init__(self):
        self.rootlogger = logging.getLogger()
        self.allurehandler = AllureLoggingHandler()
    def __enter__(self):
        if self.allurehandler not in self.rootlogger.handlers:
            self.rootlogger.addHandler(self.allurehandler)
    def __exit__(self, exc_type, exc_value, traceback):
        self.rootlogger.removeHandler(self.allurehandler)

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup():
    with AllureCatchLogs():
        yield

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call():
    with AllureCatchLogs():
        yield

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown():
    with AllureCatchLogs():
        yield

def pytest_bdd_before_scenario(feature, scenario):
    #logging.info(feature.name)
    allure.dynamic.title(scenario.name)
    allure.dynamic.feature(feature.name)
    allure.dynamic.suite(feature.name)

@pytest.fixture 
def ctx():
    return {}
@pytest.fixture
def cloudevent():
    return {}
@pytest.fixture
def trace_data():
    return {}
@pytest.fixture()
def http_response(): 
    return {}

def async_to_sync(fn):
    """Convert async function to sync function."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))

    return wrapper


@scenario('lifecycle.feature','Validate Mindwm custom resource definitions')
def test_scenario():
    assert False

@given("a kubernetes cluster$")
def kubernetes_cluster(kube, step):
    with allure.step(f"Given {step.text}"):
        cluster_info = utils.execute_and_attach_log("kubectl cluster-info")
        pass
    pass

@allure.step("Check that all nodes in kubernetes are ready")
@then("all nodes in kubernetes are ready")
def kubernetes_nodes(kube):
    with allure.step(f"Check kubernetes nodes"):
        for node in kube.get_nodes().values():
            with allure.step(f"Node '{node.name}'"):
                node_is_ready = node.is_ready()
                node_instance = node.obj
                with allure.step(f"Kubernetes node '{node.name}' are {node_is_ready}"):
                    logging.info(f"Version {node_instance.status.node_info.kubelet_version}")
                    logging.info(f"Kernel version {node_instance.status.node_info.kernel_version}")
                    pass

                assert(node_is_ready), f"{node.name} is not ready"
            pass
    pass


@scenario('0_1_mindwm_eda.feature','Validate Mindwm custom resource definitions')
def test_mindwm():
    return True

@given('a MindWM environment')
def mindwm_environment(step):
    """ change test name, using fixture names """
    with allure.step(f"given {step.text}"):
        pass

@then('following CRD should exists')
def crd_should_exists(kube, step):
    with allure.step(f"then {step.text}"):
        title_row, *rows = step.data_table.rows
        for row in rows:
            plural = row.cells[0].value
            group = row.cells[1].value
            version = row.cells[2].value
            with allure.step(f"check CRD {plural}.{group}/{version}"):
                utils.custom_object_plural_wait_for(kube, group, version, plural)
                kube.get_custom_objects(group = group, version = version, plural = plural, all_namespaces = True)
                utils.execute_and_attach_log(f"kubectl describe crd {plural}.{group}")
                pass
        pass


@when("God creates a MindWM context with the name \"{context_name}\"")
def mindwm_context(ctx, kube, context_name):
    ctx['context_name'] = context_name
    mindwm_crd.context_create(kube, context_name)
    with allure.step(f"Create context '{context_name}'"):
        pass


@then("the context should be ready and operable")
def minwdm_context_validate(ctx, kube):
    try:
        mindwm_crd.context_validate(kube, ctx['context_name'])
        with allure.step(f"Context '{ctx['context_name']}' is ready"):
            pass
    except AssertionError as e:
        # known bug https://github.com/mindwm/mindwm-gitops/issues/100
        if str(e) == f"Context {ctx['context_name']} is not ready":
            pass
        else:
            raise

@when("God creates a MindWM user resource with the name \"{user_name}\" and connects it to the context \"{context_name}\"")
def mindwm_user_create(ctx, kube, user_name, context_name):
    ctx['user_name'] = user_name
    mindwm_crd.user_create(kube, user_name, context_name)
    with allure.step(f"Create user '{user_name}' with context {context_name}"):
        pass

@then("the user resource should be ready and operable")
def mindwm_user_validate(ctx, kube):
    user = mindwm_crd.user_get(kube, ctx['user_name'])
    try:
        user.validate()
        with allure.step(f"User '{ctx['user_name']}' is ready"):
            pass
    except AssertionError as e:
        # known bug https://github.com/mindwm/mindwm-gitops/issues/100
        if str(e) == f"User {ctx['user_name']} is not ready":
            pass
        else:
            raise


@when("God creates a MindWM host resource with the name \"{host_name}\" and connects it to the user \"{user_name}\"")
def mindwm_host_create(ctx, kube, host_name, user_name):
    ctx['host_name'] = host_name
    mindwm_crd.host_create(kube, host_name, user_name)
    with allure.step(f"Host '{ctx['host_name']}' has created"):
        pass

@then("the host resource should be ready and operable")
def mindwm_host_validate(ctx, kube):
    host_name = ctx['host_name']
    host = mindwm_crd.host_get(kube, host_name)
    try:
        host.validate()
    except AssertionError as e:
        # known bug https://github.com/mindwm/mindwm-gitops/issues/100
        if str(e) == f"Host {ctx['host_name']} is not ready":
            pass
        else:
            raise

@when("God deletes the MindWM host resource \"{host_name}\"")
def mindwm_host_delete(kube, host_name):
    host = mindwm_crd.host_get(kube, host_name)
    host.delete(None)
    with allure.step(f"Mindwm host {host_name} delete"):
        pass

@then("the host \"{host_name}\" should be deleted")
def mindwm_host_deleted(kube, host_name):
    try:
        host = mindwm_crd.host_get(kube, host_name)
    except kubernetes.client.exceptions.ApiException as e:
        if e.status == 404:
            with allure.step(f"Mindwm host '{host_name}' has been deleted"):
                pass
            return True
        else:
            raise
    host.wait_until_deleted(timeout=30)
    with allure.step(f"Mindwm host {host_name} has been deleted"):
        pass


@when("God deletes the MindWM user resource \"{user_name}\"")
def mindwm_user_delete(kube, user_name):
    user = mindwm_crd.user_get(kube,user_name)
    user.delete(None)
    with allure.step(f"Mindwm user {user_name} delete"):
        pass
@then("the user \"{user_name}\" should be deleted")
def mindwm_user_deleted(kube, user_name):
    try:
        user = mindwm_crd.user_get(kube,user_name)
    except kubernetes.client.exceptions.ApiException as e:
        if e.status == 404:
            with allure.step(f"Mindwm user '{user_name}' has been deleted"):
                pass
            return True
        else:
            raise
    user.wait_until_deleted()
    with allure.step(f"Mindwm user {user_name} has been deleted"):
        pass

@when("God deletes the MindWM context resource \"{context_name}\"")
def mindwm_context_delete(kube, context_name):
    context = mindwm_crd.context_get(kube, context_name)
    context.delete(None)
    with allure.step(f"Mindwm context {context_name} delete"):
        pass
@then("the context \"{context_name}\" should be deleted")
def mindwm_context_deleted(kube, context_name):
    try:
        context= mindwm_crd.context_get(kube, context_name)
    except kubernetes.client.exceptions.ApiException as e:
        if e.status == 404:
            with allure.step(f"Mindwm context '{context_name}' has been deleted"):
                pass
            return True
        else:
            raise
    context.wait_until_deleted(30)
    with allure.step(f"Mindwm context {context_name} has been deleted"):
        pass

@then('the following resources of type "{resource_type}" has a status "{status_name}" equal "{status}" in "{namespace}" namespace')
def following_resource_status_equal(kube, resource_type, status_name, status, namespace, step):
    title_row, *rows = step.data_table.rows
    for row in rows:
        resource_name = row.cells[0].value
        resource_status_equal(kube, resource_name, resource_type, status_name, status, namespace, step) 



@then('resource "{resource_name}" of type "{resource_type}" has a status "{status_name}" equal "{status}" in "{namespace}" namespace')
def resource_status_equal(kube, resource_name, resource_type, status_name, status, namespace, step):

    with allure.step(f'then {step.text}'):
        plural, group, version = re.match(r"([^\.]+)\.(.+)/(.+)", resource_type).groups()
        utils.custom_object_status_waiting_for(
            kube,
            namespace,
            group,
            version,
            plural,
            resource_name,
            status_name,
            status,
            120
            )
        pass

@given("an Ubuntu {ubuntu_version} system with {cpu:d} CPUs and {mem:d} GB of RAM")
def environment(ctx, ubuntu_version, cpu, mem):
    ctx['cpu'] = cpu
    ctx['mem'] = mem
    ctx['ubuntu_version'] = ubuntu_version
    assert(cpu >= 6), f"Cpu < 6"
    assert(mem >= 16), f"Mem < 16"
    assert(ubuntu_version == "22.04" or ubuntu_version == "24.04")
    pass

@given("the mindwm-gitops repository is cloned into the \"{repo_dir}\" directory")
def mindwm_repo(ctx, repo_dir):
    ctx['repo_dir'] =  os.path.expanduser(repo_dir)
    assert(os.path.isdir(ctx['repo_dir'])), f"No such directory {ctx['repo_dir']}"
    pass

@when("God executes \"make {target_name}\"")
def run_make(ctx, target_name):
    with allure.step(f"make {target_name}"):
        pass
    utils.run_cmd(f"make {target_name}", ctx['repo_dir'])

@then("helm release \"{helm_release}\" is deployed in \"{namespace}\" namespace" )
def helm_release_deployed(kube, helm_release, namespace, step):
    with allure.step(f"then {step.text}"):
        info = utils.helm_release_is_ready(kube, helm_release, namespace)
        assert(info['status'] == "deployed")

@then("the argocd \"{application_name}\" application appears in \"{namespace}\" namespace")
def argocd_application(kube, application_name, namespace):
    utils.argocd_application(kube, application_name, namespace)
    with allure.step(f"Argocd application '{application_name}' exist"):
        pass

@then("the argocd \"{application_name}\" application is {namespace} namespace in a progressing status")
def argocd_application_in_progress(kube, application_name, namespace):
    utils.argocd_application_wait_status(kube, application_name, namespace)
    argocd_app = utils.argocd_application(kube, application_name, namespace)
    health_status = argocd_app['status']['health']['status']
    with allure.step(f"Argocd application '{application_name}' is {health_status}"):
        pass
    logging.info(f"{application_name} {health_status}")
    # @metacoma(TODO) Progressing only
    assert(health_status == 'Progressing' or health_status == "Healthy") or health_status == "Missing"


@then("all argocd applications are in a healthy state")
def argocd_applications_check(kube, step):
    title_row, *rows = step.data_table.rows

    for row in rows:
        application_name = row.cells[0].value
        argocd_application_in_progress(kube, application_name, "argocd")
        with allure.step(f"Argocd application '{application_name}' is healty"):
            pass

@then("the following roles should exist:")
def role_exist(kube, step):
    title_row, *rows = step.data_table.rows
    cluster_roles = kube.get_clusterroles()
    for row in rows:
        role_name = row.cells[0].value 
        role = cluster_roles.get(role_name)
        assert role is not None, f"Role {role_name} not found"
        with allure.step(f"Role '{role_name}' exist"):
            pass


@then("namespace \"{namespace}\" should exist")
def namespace_exist(ctx, kube, namespace, step):
    ctx['namespace'] = namespace
    with allure.step(f"then {step.text}"):
        try:
            ns = Namespace.new(namespace)
            ns.wait_until_ready(timeout=60)
        except Exception as e:
            utils.execute_and_attach_log("kubectl get ns")
            raise e
        pass

@then("namespace \"{namespace}\" should not exist")
def namespace_not_exist(kube, namespace):
    try:
        ns = Namespace.new(namespace)
    except kubernetes.client.exceptions.ApiException as e:
        if e.status == 404:
            with allure.step(f"Namespace '{namespace}' has been deleted"):
                pass
            return True
        else:
            raise

    ns.wait_until_deleted(timeout=180)
    with allure.step(f"Namespace '{namespace}' has been deleted"):
        pass


@then("statefulset \"{statefulset_name}\" in namespace \"{namespace}\" is in ready state")
def statefulset_is_ready(kube, statefulset_name, namespace, step):
    with allure.step(f"then {step.text}"):
        statefulset = utils.statefulset_wait_for(kube, statefulset_name, namespace)
        with allure.step(f"waiting for statefulset {statefulset_name} is ready"):
            try:
                statefulset.wait_until_ready(180)
            except Exception as e:
                utils.execute_and_attach_log(f"kubectl -n {namespace} get statefulset")
                raise e

@then("the following knative services are in a ready state in the \"{namespace}\" namespace")
def knative_service_exist(kube, step, namespace):
    title_row, *rows = step.data_table.rows
    for row in rows:
        service_name = row.cells[0].value 
        service = utils.knative_service_wait_for(kube, service_name, namespace)
        is_ready = utils.resource_get_condition(service['status'], 'Ready')
        with allure.step(f"Knative service '{namespace}'/'{service_name}' ready state is {is_ready}"):
            pass
        assert(is_ready), f"Knative service '{namespace}'/{service_name} is not ready"

@then("the following knative triggers are in a ready state in the \"{namespace}\" namespace")
def knative_trigger_exist(kube, step, namespace):
    title_row, *rows = step.data_table.rows
    for row in rows:
        trigger_name = row.cells[0].value 
        trigger = utils.knative_trigger_wait_for(kube, trigger_name, namespace)
        is_ready = utils.resource_get_condition(trigger['status'], 'Ready')
        with allure.step(f"Knative trigger '{trigger_name}' ready state is {is_ready}"):
            pass
        assert(is_ready == 'True')

@when("sends cloudevent to \"{broker_name}\" in \"{namespace}\" namespace")
def event_send_ping(kube, step, cloudevent, broker_name, namespace):
    payload = json.loads(step.doc_string.content)

    ingress_host = utils.get_lb(kube)
    url = f"http://{ingress_host}/{namespace}/{broker_name}"

    headers = {
        **{
            "Content-Type": "application/json",
            "Ce-specversion": "1.0",
        }, 
        **cloudevent['headers']
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    assert response.status_code == 202, f"Unexpected status code: {response.status_code}"

    pass

@then("the trace with \"{traceparent}\" should appear in TraceQL")
def tracesql_get_trace(kube, traceparent, trace_data):
    ingress_host = utils.get_lb(kube)
    trace_id = utils.extract_trace_id(traceparent) 
    url = f"http://{ingress_host}/api/traces/{trace_id}"
    headers = {
        "Host": "tempo.mindwm.local"
    }
    time.sleep(10)
    response = requests.get(url, headers = headers)
    assert response.status_code == 200, f"Response code {response.status_code} != 200"
    tempo_reply = json.loads(response.text)
    trace_resourceSpans = {
                "resourceSpans": tempo_reply['batches']
    }
    allure.attach(json.dumps(tempo_reply), name = "Tempo reply", attachment_type='application/json')
    trace_data['data'] = ParseDict(trace_resourceSpans, trace_pb2.TracesData())

@then("the trace should contains")
def trace_should_contains(step, trace_data):
    logging.debug(f"TRACE DATA = {trace_data['data']}")
    title_row, *rows = step.data_table.rows
    for row in rows:
        service_name = row.cells[0].value 
        #http_code = row.cells[1].value 
        #http_path = row.cells[2].value 
        #logging.debug(f"{service_name} {http_code} {http_path}")
        scope_span = utils.span_by_service_name(trace_data['data'], service_name)
        logging.debug(f"Scope span {service_name} not found in trace data")
        assert(scope_span is not None), f"Scope span {service_name} not found in trace data"
        span = utils.parse_resourceSpan(scope_span)
        logging.debug(f"Span {service_name} not found in trace data")
        assert(span is not None), f"Span {service_name} not found in trace data"
        assert(span['service_name'] == service_name) 
        # assert(span['http_code'] == http_code) 
        # assert(span['http_path'] == http_path) 
    pass

@then("a cloudevent with type == \"{cloudevent_type}\" should have been received from the NATS topic \"{topic_name}\"")
def cloudvent_check(cloudevent_type, topic_name):
    time.sleep(10)
    message_queue = nats_reader.message_queue
    # copy data from message_queue to nats_queue

    while True:
        try:
            message = message_queue.get(timeout=1)
            nats_messages.append(message)
            message_queue.task_done()
        except Empty:
            break
        
    for msg in nats_messages:
        subject = msg['subject']
        data = msg['data']
        if (subject == topic_name):
            event = json.loads(data) 
            if (event['type'] == cloudevent_type):
                with allure.step(f"{cloudevent_type} exist in nats topic {topic_name}"):
                    pass
                return True

    assert False, f"There is no {cloudevent_type} in nats topic in {topic_name}"

@then("cleanup nats messages")
def nats_messages_cleanup():
    nats_messages = []

@when("God starts reading message from NATS topic \"{nats_topic_name}\"")
def nats_message_receive(kube, nats_topic_name):
    ingress_host = utils.get_lb(kube)
    nats_reader.main(f"nats://root:r00tpass@{ingress_host}:4222", nats_topic_name)
    with allure.step(f"Start nats reader from the topic {nats_topic_name}"):
        pass

@then("the following deployments are in a ready state in the \"{namespace}\" namespace")
def deployment_ready(kube, step, namespace):
    title_row, *rows = step.data_table.rows
    for row in rows:
        deployment_name = row.cells[0].value 
        with allure.step(f"then {step.text} {deployment_name}"):
            try:
                deployment = utils.deployment_wait_for(kube, deployment_name, namespace)
            except Exception as e:
                raise e
            with allure.step(f"waiting for {deployment_name} is ready"):
                try:
                    deployment.wait_until_ready(180)
                except Exception as e:
                    utils.execute_and_attach_log(f"kubectl -n {namespace} get pods")
                    utils.execute_and_attach_log(f"kubectl -n {namespace} get deployment")
                    raise e

@then("graph have node \"{node_type}\" with property \"{prop}\" = \"{value}\" in context \"{context_name}\"")
def graph_check_node(kube, node_type, prop, value, cloudevent, context_name):
    ingress_host = utils.get_lb(kube)
    bolt_port = utils.neo4j_get_bolt_node_port(kube, context_name)
    assert bolt_port is not None, f"No node_port for neo4j bolt service"
    uri = f"bolt://{ingress_host}:{bolt_port}"
    auth = ("neo4j", "password")

    traceparent_id = utils.extract_trace_id(cloudevent['headers']['traceparent'])

    with GraphDatabase.driver(uri, auth=auth) as driver:
        driver.verify_connectivity()
        records, summary, keys = driver.execute_query(f"""
            MATCH (n:{node_type})
            WHERE n.traceparent CONTAINS "-{traceparent_id}-"
            RETURN n
            """,
            database_="neo4j",
        )
        assert len(records) == 1

        for node in records:
            logging.debug(node)
            assert node['n'][prop] == value
            with allure.step(f"Node '{node_type}' has property {prop} == {value} in {context_name}"):
                pass

@when("God creates a new cloudevent")
def cloudevent_create_cloudevent(step, cloudevent):
    cloudevent['headers'] = {
        "ce-id": str(uuid.uuid4()),
        "ce-specversion": "1.0",
    }

    cloudevent['data'] = ""
@when("sets cloudevent header \"{header_name}\" to \"{value}\"")
def cloudevent_header_set(cloudevent, header_name, value):
    cloudevent['headers'][header_name] = value

@when("sends cloudevent to knative service \"{knative_service_name}\" in \"{namespace}\" namespace")
def cloudevent_send_to_ksvc(step, http_response, kube, cloudevent, knative_service_name, namespace):
    cloudevent['data'] = json.loads(step.doc_string.content)
    ksvc = utils.ksvc_url(kube, namespace, knative_service_name)
    url = ksvc['status']['url']

    headers = {
        **{
            "Content-Type": "application/json",
            "Ce-specversion": "1.0",
        }, 
        **cloudevent['headers']
    }

    http_response['answer'] = requests.post(url, headers=headers, data=json.dumps(cloudevent['data']))

@then("the response http code should be \"{code}\"")
def http_response_code_check(http_response, code):
    status_code = str(http_response['answer'].status_code)
    assert status_code == code, f"HTTP status code {status_code} != {code}"

@when("sends cloudevent to \"{endpoint}\"")
def cloudevent_send(step, kube, http_response, cloudevent, endpoint):
    cloudevent['data'] = json.loads(step.doc_string.content)
    (host, path) = endpoint.split("/", 1)
    assert host is not None, f"Host in {endpoint} is None"
    assert path is not None, f"Path in {endpoint} is None"
    
    ingress_host = utils.get_lb(kube)
    url = f"http://{ingress_host}/{path}"

    headers = {
        **{
            "Host": f"{host}.svc.cluster.local",
            "Content-Type": "application/json",
            "Ce-specversion": "1.0",
            "Ce-id": str(uuid.uuid4()),
        }, 
        **cloudevent['headers']
    }

    http_response['answer'] = requests.post(url, headers=headers, data=json.dumps(cloudevent['data']))


@when("God makes graph query in context \"{context_name}\"")
def graph_query(kube, context_name, step):
    q = step.doc_string.content

    ingress_host = utils.get_lb(kube)
    bolt_port = utils.neo4j_get_bolt_node_port(kube, context_name)
    assert bolt_port is not None, f"No node_port for neo4j bolt service"

    uri = f"bolt://{ingress_host}:{bolt_port}"
    auth = ("neo4j", "password")

    with GraphDatabase.driver(uri, auth=auth) as driver:
        driver.verify_connectivity()
        records, summary, keys = driver.execute_query(q, database_="neo4j")
 
@when("sends cloudevent to nats topic \"{nats_topic_name}\"")
@async_to_sync
async def cloudevent_to_nats_topic(step, kube, nats_topic_name, cloudevent):
    payload = step.doc_string.content
    ingress_host = utils.get_lb(kube)
    nats_url = f"nats://root:r00tpass@{ingress_host}:4222"
    await utils.nats_send(nats_url, nats_topic_name, cloudevent['headers'], str.encode(payload))
 
def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]):
     # XXX workaround
     for item in items:
         item.add_marker(pytest.mark.namespace(create = False, name = "default"))
 
@then('istio-gateway "{istio_gateway_name}" exists in "{namespace_name}" namespace')
def istio_gateway(kube, istio_gateway_name, namespace_name, step):
    utils.custom_object_exists(
        kube,
        namespace_name,
        'networking.istio.io',
        "v1beta1",
        "gateways",
        istio_gateway_name,
        60
    )

@then('the following istio-virtualservice exists in the "{namespace_name}" namespace')
def istio_gateway(kube, istio_gateway_name, namespace_name, step):
    title_row, *rows = step.data_table.rows
    for row in rows:
        virtualservice_name = row.cells[0].value 
        virtualservice = utils.custom_object_exists(
            kube,
            namespace_name,
            'networking.istio.io',
            "v1",
            "virtualservices",
            virtualservice_name,
            60
        )
@then('container "{container_name}" in pod "{pod_name_regex}" in namespace "{namespace}" should contain "{log_regex}" regex')
def pod_container_shoult_contain_regex(kube, namespace, pod_name_regex, container_name, log_regex, step):
    pod_logs_should_contain_regex(namespace, pod_name_regex, container_name, log_regex)


@then('container "{container_name}" in pod "{pod_name_regex}" in namespace "{namespace}" should not contain "{log_regex}" regex')
def pod_container_should_not_contain_regex(kube, namespace, pod_name_regex, container_name, log_regex, step):
    pod_logs_should_not_contain_regex(namespace, pod_name_regex, container_name, log_regex)

@then('file "{file_path}" contain "{match_regex}" regex')
def file_contains_regex(file_path, match_regex):
    with open(file_path, 'r') as file:
            content = file.read()
            if re.search(match_regex, content):
                return True
            else:
                raise ValueError

@when("God clones the repository '{repo}' with branch '{branch}' and commit '{commit}' to '{work_dir}'")
def git_clone_repo(repo, branch, commit, work_dir):
    git_clone(work_dir, repo, branch, commit)
    pass

@then("the directory '{dir_path}' should exist")
def dir_exists(dir_path):
    if os.path.isdir(dir_path):
        logging.debug(f"Directory '{dir_path}' exists.")
    else:
        raise FileNotFoundError(f"Directory '{dir_path}' does not exist.")
    pass

@when("God runs the command '{cmd}' inside the '{work_dir}' directory")
def execute_cmd(cmd, work_dir):
    utils.run_cmd(cmd, work_dir)
    pass

@when("God creates a tmux session named '{tmux_session}' with a window named '{tmux_window_name}'")
def tmux_create_sesion(tmux_session, tmux_window_name):
    r = create_tmux_session(tmux_session, tmux_window_name, work_dir)
    if (r is None):
        assert RuntimeError
    pass

@then("the tmux session '{tmux_session}' should exist")
def tmux_check_session(tmux_session):
    r = tmux_session_exists(tmux_session)
    if (r is not True):
        raise RuntimeError
    pass

@then("God sends the command '{cmd}' to the tmux session '{tmux_session}', window '{tmux_window_name}', pane '{tmux_pane_id}'")
def tmux_send_command(tmux_session, tmux_window_name, tmux_pane_id, cmd):
    r = send_command_to_pane(tmux_session, tmux_window_name, int(tmux_pane_id), cmd)
    if (r is None):
        assert RuntimeError
    pass

@then("God waits for '{n}' seconds")
def sleep_n_seconds(n):
    time.sleep(int(n))
    pass

@then("God vertically splits the tmux session '{tmux_session}', window '{tmux_window_name}'")
def tmux_vertically_split(tmux_session, tmux_window_name):
    r = vertically_split_window(tmux_session, tmux_window_name)
    if (r is None):
        assert RuntimeError
    pass
