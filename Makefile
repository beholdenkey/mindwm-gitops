.PHONY: argocd

ARGOCD_HOST_PORT := 38080

KUBECTL_RUN := docker run --rm -v ~/.kube:/kube -e KUBECONFIG=/kube/config --network=host -v`pwd`:/host -w /host -u root --entrypoint /bin/sh bitnami/kubectl:latest -c
HELM_RUN := docker run --rm -v ~/.kube:/root/.kube -e KUBECONFIG=/root/.kube/config --network=host -v`pwd`:/host -w /host --entrypoint /bin/sh alpine/helm:latest -c


#helm upgrade --install --namespace argocd --create-namespace argocd argocd/argo-cd --set global.image.tag=v2.9.12 --set repoServer.extraArguments[0]="--repo-cache-expiration=1m",repoServer.extraArguments[1]="--default-cache-expiration=1m",repoServer.extraArguments[2]="--repo-server-timeout-seconds=240s"  --wait --timeout 5m && \

fix_dns_upstream:
	$(KUBECTL_RUN) '\
		kubectl -n kube-system get configmap coredns -o yaml | sed "s,forward . /etc/resolv.conf,forward \. 8.8.8.8," | kubectl apply -f - && \
		kubectl delete pod -n kube-system -l k8s-app=kube-dns \
	'

crossplane_rolebinding_workaround:
	$(KUBECTL_RUN) '\
		for i in kcl-function provider-kubernetes provider-helm; do \
			SA=`kubectl -n crossplane-system get sa -o name | grep $$i | sed -e "s|serviceaccount\/|crossplane-system:|g"`; \
			test -n "$$SA" || continue; \
			kubectl get clusterrolebinding $$i-admin-binding || kubectl create clusterrolebinding $$i-admin-binding --clusterrole cluster-admin --serviceaccount=$$SA; \
		done;\
		SA=crossplane-system:crossplane && \
		i=crossplane && \
		kubectl get clusterrolebinding $$i-admin-binding || kubectl create clusterrolebinding $$i-admin-binding --clusterrole cluster-admin --serviceaccount=$$SA \
	'

deinstall:
	k3s-uninstall.sh ; \
	sleep 10 # :)

cluster: deinstall
	curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --disable=traefik" sh -s - --docker && sleep 30 && \
	sudo cat /etc/rancher/k3s/k3s.yaml > ~/.kube/config && \
	$(MAKE) fix_dns_upstream


argocd:
	$(HELM_RUN) "\
		helm repo add argocd https://argoproj.github.io/argo-helm && \
		helm repo update argocd && \
		helm upgrade --install --namespace argocd --create-namespace argocd argocd/argo-cd -f ./argocd_values.yaml --set server.service.servicePortHttp=$(ARGOCD_HOST_PORT) --wait --timeout 5m \
	"
	$(KUBECTL_RUN) '\
		kubectl apply -f ./kcl-cmp.yaml && \
		kubectl -n argocd patch deploy/argocd-repo-server -p "`cat ./patch-argocd-repo-server.yaml`" && \
		kubectl wait --for=condition=ready pod -n argocd -l app.kubernetes.io/name=argocd-repo-server --timeout=600s \
	'

kcl_tini:
	docker build -t metacoma/kcl-tini:latest -f kcl_tini.Dockerfile .

#.PHONY: kubectl_proxy
#kubectl_proxy:
#	pkill -9 -f "^kubectl port-forward service/argocd-server -n argocd 8080:443";\
#	kubectl port-forward service/argocd-server -n argocd 8080:443 &

kcl_plugin_context:
	kubectl -n argocd exec -it `kubectl -n argocd get pod -l app.kubernetes.io/component=repo-server -o name` -c my-plugin -- /bin/bash
kcl_log:
	kubectl -n argocd logs -f `kubectl -n argocd get pod -l app.kubernetes.io/component=repo-server -o name` -c repo-server
my_plugin:
	kubectl -n argocd logs -f `kubectl -n argocd get pod -l app.kubernetes.io/component=repo-server -o name` -c my-plugin

function_kcl_exec:
	kubectl -n crossplane-system exec -ti `kubectl -n crossplane-system get pods -l pkg.crossplane.io/function=function-kcl -o name` -- /bin/bash

copy_prog:
	$(eval FUNCTION_KCL_POD := $(shell kubectl -n crossplane-system get pods -l pkg.crossplane.io/function=function-kcl -o name))
	$(eval LAST_FILE := $(shell kubectl -n crossplane-system exec -ti $(FUNCTION_KCL_POD) -- sh -c "ls -ltr /tmp | sed -nr '$$ s,.* (sandbox.*),/tmp/\1/prog.k,p'"))
	kubectl -n crossplane-system exec $(FUNCTION_KCL_POD) -- cat $(LAST_FILE)

stuck_ns:
	kubectl get namespace "$(DELETE_NS)" -o json \
	  | tr -d "\n" | sed "s/\"finalizers\": \[[^]]\+\]/\"finalizers\": []/" \
  		| kubectl replace --raw /api/v1/namespaces/$(DELETE_NS)/finalize -f -




#.PHONY: argocd_password
argocd_password:
	$(eval ARGOCD_PASSWORD := $(shell $(KUBECTL_RUN) 'kubectl get secret -n argocd argocd-initial-admin-secret -o jsonpath="{.data.password}"  |base64 -d;echo'))
	echo $(ARGOCD_PASSWORD)

#.PHONY: argocd_login
argocd_login: argocd_password
	argocd login --insecure --username admin --password $(ARGOCD_PASSWORD) localhost:8080

argocd_app_run_and_wait: argocd_password
	$(KUBECTL_RUN) "kubectl -n argocd exec -ti deployment/argocd-server -- sh -c 'argocd login --plaintext --username admin --password $(ARGOCD_PASSWORD) localhost:8080 && argocd app sync mindwm-gitops'"

argocd_exec: argocd_password
	@echo kubectl -n argocd exec -ti deployment/argocd-server -- sh -c 'argocd login --plaintext --username admin --password $(ARGOCD_PASSWORD) localhost:8080 && argocd app sync mindwm-gitops'
	kubectl -n argocd exec -ti deployment/argocd-server -- bash


.PHONY: argocd_app
argocd_app: argocd
	$(KUBECTL_RUN) 'kubectl apply -f argocd_mindwm_app.yaml'

argocd_sync: argocd_app argocd_login
	argocd app sync mindwm-gitops

mindwm_lifecycle: cluster argocd_app argocd_app_run_and_wait crossplane_rolebinding_workaround

