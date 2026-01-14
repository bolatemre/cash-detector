docker compose exec master-service python -c "
import requests, sys
try:
    url = 'http://keycloak:8080/realms/security-realm/protocol/openid-connect/token'
    data = {
        'client_id': 'master-service',
        'client_secret': 'master-service-secret',
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, data=data)
    response.raise_for_status()
    print(response.json())
except requests.exceptions.RequestException as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
"