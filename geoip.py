import aiohttp
import asyncio

_cache = {}
_cache_ttl = 3600

async def get_geo_info(ip_address: str) -> dict:
    if not ip_address or ip_address in ("127.0.0.1", "::1", "localhost"):
        return {"country": "", "city": "", "is_vpn": False, "org": ""}

    if ip_address in _cache:
        import time
        cached = _cache[ip_address]
        if time.time() - cached["ts"] < _cache_ttl:
            return cached["data"]

    result = {"country": "", "city": "", "is_vpn": False, "org": ""}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://ip-api.com/json/{ip_address}?fields=status,country,countryCode,city,isp,org,proxy,hosting",
                timeout=aiohttp.ClientTimeout(total=4)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success":
                        result = {
                            "country": data.get("countryCode", ""),
                            "city": data.get("city", ""),
                            "is_vpn": data.get("proxy", False) or data.get("hosting", False),
                            "org": data.get("org", "") or data.get("isp", ""),
                        }
    except Exception:
        pass

    import time
    _cache[ip_address] = {"data": result, "ts": time.time()}
    return result


def extract_ip(request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return ""
