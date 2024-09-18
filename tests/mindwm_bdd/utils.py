import pprint
import base64
import gzip
import json
from io import BytesIO
from kubernetes import client, config
from kubetest import condition
from kubetest import utils as kubetest_utils

def double_base64_decode(encoded_str):
    try:
        first_decode = base64.b64decode(encoded_str)
        second_decode = base64.b64decode(first_decode)
        return second_decode
    except base64.binascii.Error as e:
        print(f"Base64 decoding error: {e}")
        return None

def gunzip_data(compressed_data):
    try:
        with gzip.GzipFile(fileobj=BytesIO(compressed_data)) as gz:
            decompressed_data = gz.read()
            return decompressed_data
    except OSError as e:
        print(f"Gunzip error: {e}")
        return None


def helm_release_info(kube, release_name, namespace):
    helm_secret = kube.get_secrets(namespace, labels = {"name": release_name})[f'sh.helm.release.v1.{release_name}.v1']
    #release_str = json.loads(helm_secret.obj.data)
    data_base64 = helm_secret.obj.data['release']
    data_str = gunzip_data(double_base64_decode(data_base64))
    data = json.loads(data_str)
    return data['info']

def helm_release_is_ready(kube, release_name, namespace):
    def is_ready():
        try:
            info = helm_release_info(kube, release_name, namespace)
            return info['status'] == "deployed"
        except Exception as e:
            pprint.pprint(e)
            return False

    ready_condition = condition.Condition("helm release has status and info", is_ready)

    kubetest_utils.wait_for_condition(
        condition=ready_condition,
        timeout=180,
        interval=5
    )


    return helm_release_info(kube, release_name, namespace)


    
def argocd_application(kube, application_name, namespace):
    api_instance = client.CustomObjectsApi(kube.api_client)
    resource = api_instance.get_namespaced_custom_object(
        group='argoproj.io',
        version='v1alpha1',
        plural='applications',
        namespace = namespace,
        name = application_name
        )
    return resource

def argocd_application_wait_status(kube, application_name, namespace):
    def has_status(): 
        try:
            resource = argocd_application(kube, application_name, namespace),
            sync_status = resource[0]['status']['sync']
            health_status = resource[0]['status']['health']['status']
            #pprint.pprint(health_status)
            return True
        except Exception as e: 
            #pprint.pprint(e)
            return False
            
    status_condition = condition.Condition("api object deleted", has_status)

    # 07:h8
    kubetest_utils.wait_for_condition(
        condition=status_condition,
        timeout=180,
        interval=5
    )


