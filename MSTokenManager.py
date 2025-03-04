from msal import ConfidentialClientApplication
import os
from typing import Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class MSTokenManager():
    token: Any = None
    client_id = os.getenv("AZURE_APPLICATION_CLIENT_ID")
    client_secret = os.getenv("AZURE_APPLICATION_CLIENT_SECRET")
    tenant_id = os.getenv("AZURE_APPLICATION_TENANT_ID")
    scopes = os.getenv("AZURE_APPLICATION_SCOPES", "").split(" ")
    print(f"Tenant ID: {os.getenv('AZURE_APPLICATION_TENANT_ID')}")


    def __init__(self, client_id: str=None, client_secret: str=None, tenant_id: str=None, scopes:list[str]=['']):
        if client_id and client_secret and tenant_id:
            authority = f"https://login.microsoftonline.com/{tenant_id}"
            self.app = ConfidentialClientApplication(client_id, client_credential=client_secret, authority=authority)

        else:
            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            self.app = ConfidentialClientApplication(self.client_id, client_credential=self.client_secret, authority=authority)

        if scopes != ['']:
            self.scopes=scopes


    def get_token(self):
        self.token = self.app.acquire_token_for_client(scopes=self.scopes)
        return self.token['access_token']

