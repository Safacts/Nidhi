import requests
token_url = 'http://172.21.0.1:8000/o/token/'
data = {
    'grant_type': 'password',
    'username': 'aadi',
    'password': 'SHESHU1.',
    'client_id': 'nidhi_client_id_123',
    'client_secret': 'nidhi_client_secret_xyz789_very_long_string_for_security',
}
r = requests.post(token_url, data=data)
if r.status_code == 200:
    token = r.json()['access_token']
    introspect_url = 'http://172.21.0.1:8000/o/introspect/'
    idata = {
        'token': token,
        'client_id': 'nidhi_client_id_123',
        'client_secret': 'nidhi_client_secret_xyz789_very_long_string_for_security'
    }
    r2 = requests.post(introspect_url, data=idata)
    print('Introspect:', r2.status_code, r2.text)
else:
    print('Token err:', r.text)
