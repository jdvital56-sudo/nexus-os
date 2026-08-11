import httpx
import logging
import os
from typing import Optional, Dict, List, Any
from backend.core.config import APOLLO_API_KEY

logger = logging.getLogger(__name__)

class ApolloClient:
    def __init__(self):
        self.api_key = APOLLO_API_KEY
        self.base_url = "https://api.apollo.io/v1"
        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        } if self.api_key else {}
        
        if not self.api_key:
            logger.warning("APOLLO_API_KEY not set. Apollo features disabled.")

    async def search_people(
        self, 
        keywords: Optional[str] = None, 
        organization_names: Optional[List[str]] = None,
        page: int = 1,
        per_page: int = 25
    ) -> Dict[str, Any]:
        """Поиск контактов по ключевым словам или компаниям"""
        if not self.api_key:
            return {"error": "Apollo API key not configured"}

        payload = {
            "page": page,
            "per_page": per_page,
            "person_titles": ["founder", "ceo", "cto", "director"],
        }
        
        if keywords:
            payload["q_organization_domains"] = keywords
        if organization_names:
            payload["organization_names"] = organization_names

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/people/search",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                return {"error": f"Apollo API error: {str(e)}", "details": e.response.text if hasattr(e, 'response') else ""}

    async def get_person(self, person_id: str) -> Dict[str, Any]:
        """Получение данных о конкретном контакте"""
        if not self.api_key:
            return {"error": "Apollo API key not configured"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/people/{person_id}",
                    headers=self.headers,
                    timeout=10.0
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                return {"error": f"Apollo API error: {str(e)}"}

    async def search_companies(self, keywords: str, page: int = 1) -> Dict[str, Any]:
        """Поиск компаний"""
        if not self.api_key:
            return {"error": "Apollo API key not configured"}

        payload = {
            "q_organization_domains": keywords,
            "page": page,
            "per_page": 10
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/organizations/search",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                return {"error": f"Apollo API error: {str(e)}"}

    async def enrich_person(self, email: str) -> Dict[str, Any]:
        """Обогащение данных по email"""
        if not self.api_key:
            return {"error": "Apollo API key not configured"}

        payload = {"email": email}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/people/match",
                    json=payload,
                    headers=self.headers,
                    timeout=10.0
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                return {"error": f"Apollo API error: {str(e)}"}

# Singleton instance
apollo_client = ApolloClient()
