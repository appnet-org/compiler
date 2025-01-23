## Run Bookinfo Applicaton

```bash
kubectl apply -f online_boutique.yaml
kubectl get pods

# Test (Home Handler)
curl http://10.96.88.88/

# Checkout Handler
curl -X POST http://10.96.88.88/cart/checkout -d "email=test@example.com" -d "street_address=123 Main St" -d "zip_code=98101" -d "city=Seattle" -d "state=WA" -d "country=USA" -d "credit_card_number=4111111111111111" -d "credit_card_expiration_month=12" -d "credit_card_expiration_year=2025" -d "credit_card_cvv=123"

# Destroy
kubectl delete pv,pvc,sa,all --all
```