import asyncio
import math

import json
import logging
from tornado.httpclient import HTTPRequest

from crawler_utils.utils import read_prop
from notification_sender import Notification
from runner import Filter
from services.abstract_service import AbstractService


class LeBonCoin(AbstractService):

    def __init__(self, f: Filter, enable_proxy=None) -> None:
        super().__init__(f, enable_proxy)
        self.fetch_size = 35

    def get_service_name(self) -> str:
        return "LeBonCoin"

    def get_candidate_native_id(self, candidate):
        return candidate['list_id']

    async def candidate_to_notification(self, candidate) -> Notification:
        return Notification(
            price=candidate.get('price')[0],
            location=read_prop(candidate, 'location', 'zipcode'),
            area={e['key']: e['value'] for e in candidate['attributes']}.get('square'),
            url=candidate.get('url'),
            pics_urls=read_prop(candidate, 'images', 'urls_large')
        )

    async def run(self):
        first_page = await self.fetch()
        nb_pages = math.ceil(first_page['total'] / self.fetch_size)
        resp_of_pages = [r.result() for r in
                         (await asyncio.wait([self.fetch(i) for i in range(2, nb_pages + 1)]))[0]]
        for p in (resp_of_pages + [first_page]):
            for i in (read_prop(p, 'ads', fallback=[]) + read_prop(p, 'ads_alu', fallback=[])):
                await self.push_candidate(i)

    async def fetch(self, page=1):
        url = "https://api.leboncoin.fr/finder/search"
        headers = {'cache-control': 'no-cache'}
        res = await self.client.patient_fetch(
            HTTPRequest(method="POST", url=url, body=json.dumps(self.create_post_body(page)), headers=headers))
        return json.loads(res.body.decode())

    def create_post_body(self, page=1):
        locations = [
            {"city": "Paris", "zipcode": str(a), "label": f"Paris ({a})", "region_id": "12", "department_id": "75",
             "locationType": "city"}
            for a in self.filter.arrondissements]
        payload = {
            "limit": self.fetch_size, "offset": self.fetch_size * (page - 1), "limit_alu": 3, "filters": {
                "category": {"id": "10"},
                "enums": {"ad_type": ["offer"], "real_estate_type": ["1", "2"]},
                "location": {"locations": locations},
                "keywords": {},
                "ranges": {"square": {"min": self.filter.min_area},
                           "price": {"min": int(self.filter.max_price / 2), "max": self.filter.max_price}}}}

        if self.filter.furnished is not None:
            payload['filters']['enums']['furnished'] = ["1" if self.filter.furnished else "0"]

        return payload


if __name__ == '__main__':
    f = Filter(arrondissements=[75001, 75002, 75003, 75004, 75005, 75010, 75011, 75008, 75009], max_price=1300,
               min_area=25)
    coin = LeBonCoin(f, enable_proxy=False)
    res = asyncio.get_event_loop().run_until_complete(coin.run())
    logging.info(len(coin.notifications))
