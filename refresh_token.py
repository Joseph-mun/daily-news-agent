import requests

url = "https://kauth.kakao.com/oauth/token"
data = {
    "grant_type": "authorization_code",
    "client_id": "ac8df9480be3d6c849f5a7fbc58fa9ad",
    "redirect_uri": "https://localhost:3000",
    "code": "uHmW9E9xWcPwrREuWu77imWq7fH_EfKA60TqDsATEswidZYuIdc_-AAAAAQKFxKWAAABm-UuNQse0jm_MNo9Pw"
}

response = requests.post(url, data=data)
tokens = response.json()
print("refresh_token:", tokens.get("refresh_token"))
