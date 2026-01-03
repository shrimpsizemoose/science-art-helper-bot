# Kubernetes commands for workshop-signup-bot

NAMESPACE := matvey-gang
APP := workshop-signup-bot

# List pods
k8s-pods:
	kubectl get pods -n $(NAMESPACE) -l app=$(APP)

# View logs (last 100 lines)
k8s-logs:
	kubectl logs -n $(NAMESPACE) -l app=$(APP) --tail=100

# Follow logs in real-time
k8s-logs-follow:
	kubectl logs -n $(NAMESPACE) -l app=$(APP) -f

.PHONY: k8s-pods k8s-logs k8s-logs-follow
