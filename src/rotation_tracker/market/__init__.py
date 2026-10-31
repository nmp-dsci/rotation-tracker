"""s03: prices, read from market-getdata. This repo never fetches a price itself.

- ``proxies``: assets/proxies.yaml (proxies/v2), the typed series that stand for each asset;
  ``rt.asset_proxies``; the instrument list handed to market-getdata.
- ``components``: assets/components.yaml, what is inside a category.
- ``fdw``: ``market_staging``, market-getdata's ``staging`` imported over postgres_fdw.
- ``prices``: the viewer's reads of ``market_staging`` and the chart's price lines.
"""
