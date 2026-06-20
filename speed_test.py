import yaml
import json
import requests
import time
import re
import urllib3
import concurrent.futures
import copy
from collections import defaultdict

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FLAGS = {
    "US": "🇺🇸", "UK": "🇬🇧", "GB": "🇬🇧", "FR": "🇫🇷", 
    "NL": "🇳🇱", "SG": "🇸🇬", "RU": "🇷🇺", "DE": "🇩🇪"
}

TEST_URL = "http://cachefly.cachefly.net/10mb.test"
TIMEOUT = 12

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def test_candidate(cand):
    proxy_config = cand['proxy']
    server = proxy_config.get('server')
    port = proxy_config.get('port')
    scheme = "https" if proxy_config.get('tls') else "http"
    
    if 'username' in proxy_config and 'password' in proxy_config:
        proxy_url = f"{scheme}://{proxy_config['username']}:{proxy_config['password']}@{server}:{port}"
    else:
        proxy_url = f"{scheme}://{server}:{port}"

    proxies = {"http": proxy_url, "https": proxy_url}

    try:
        start = time.time()
        resp = requests.get(TEST_URL, proxies=proxies, timeout=TIMEOUT, headers=HEADERS, verify=False)
        resp.raise_for_status()
        duration = time.time() - start
        
        mbps = (len(resp.content) * 8) / duration / 1_000_000
        cand['speed'] = round(mbps, 1)
        cand['status'] = 'LIVE'
        return cand
    except Exception as e:
        cand['speed'] = 0.0
        cand['status'] = 'DEAD'
        error_msg = str(e)
        if "Read timed out" in error_msg:
            cand['error'] = "Timeout"
        elif "Max retries exceeded" in error_msg or "Connection refused" in error_msg:
            cand['error'] = "Conn Failed"
        elif "403 Client Error" in error_msg:
            cand['error'] = "Blocked 403"
        else:
            cand['error'] = "Error"
        return cand

def rebuild_clash_groups(clash_dict, name_mapping, original_names):
    if 'proxy-groups' in clash_dict:
        for group in clash_dict['proxy-groups']:
            if 'proxies' not in group: continue
            new_group_proxies = []
            for p_name in group['proxies']:
                if p_name in original_names:
                    new_group_proxies.extend(name_mapping.get(p_name, []))
                else:
                    new_group_proxies.append(p_name)
            seen = set()
            group['proxies'] = [x for x in new_group_proxies if not (x in seen or seen.add(x))]
    return clash_dict

def generate_singbox_config(live_proxies, filename="tested-singbox.json"):
    """تولید فایل سینگ‌باکس با قالب درخواستی کاربر"""
    outbounds = []
    proxy_tags = []

    for p in live_proxies:
        if p.get('type') == 'http':
            server_name = p.get('sni') or p.get('server')
            tag = p['name']
            
            singbox_proxy = {
                "type": "http",
                "tag": tag,
                "server": p['server'],
                "server_port": p['port'],
                "username": p.get('username', ''),
                "password": p.get('password', ''),
                "tls": {
                    "enabled": p.get('tls', False),
                    "server_name": server_name,
                    "insecure": p.get('skip-cert-verify', True),
                    "utls": {
                        "enabled": True,
                        "fingerprint": "chrome"
                    }
                }
            }
            outbounds.append(singbox_proxy)
            proxy_tags.append(tag)

    full_config = {
        "log": {"level": "info"},
        "dns": {
            "servers": [
                {"tag": "dns_google", "address": "8.8.8.8", "detour": "🚀 Select Server"},
                {"tag": "dns_local", "address": "1.1.1.1", "detour": "direct"}
            ]
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": "tun0",
                "inet4_address": "172.19.0.1/30",
                "auto_route": True,
                "strict_route": True,
                "sniff": True
            }
        ],
        "outbounds": [
            {
                "type": "selector",
                "tag": "🚀 Select Server",
                "outbounds": proxy_tags
            },
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"}
        ] + outbounds,
        "route": {
            "rules": [
                {"geosite": ["ir"], "outbound": "direct"},
                {"geoip": ["ir"], "outbound": "direct"}
            ],
            "auto_detect_interface": True
        }
    }

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(full_config, f, indent=2, ensure_ascii=False)

def main():
    print("Loading vpnlist.yaml...")
    try:
        with open('vpnlist.yaml', 'r', encoding='utf-8') as f:
            base_clash_data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading yaml: {e}")
        return

    original_proxies = base_clash_data.get('proxies', [])
    original_proxy_names = {p['name'] for p in original_proxies}
    candidate_list = []
    seen_server_ports = set()

    print("Offline Parsing: Generating 1 to 10 nodes for each server...")
    for old_proxy in original_proxies:
        server = old_proxy.get('server', '')
        port = old_proxy.get('port', 0)
        match = re.match(r'^([a-zA-Z0-9-]+?)(?:-\d+)?-([a-zA-Z]{2})\.maxxxcdn\.com$', server)
        
        if match:
            dc_base = match.group(1)
            country = match.group(2).upper()
            for i in range(1, 11):
                new_server = f"{dc_base}-{i}-{country.lower()}.maxxxcdn.com"
                combo = f"{new_server}:{port}"
                if combo in seen_server_ports: continue
                seen_server_ports.add(combo)
                
                new_proxy = copy.deepcopy(old_proxy)
                new_proxy['server'] = new_server
                
                candidate_list.append({
                    'proxy': new_proxy, 'old_name': old_proxy['name'],
                    'dc_base': dc_base, 'country': country, 'num': i, 'port': port
                })
        else:
            combo = f"{server}:{port}"
            if combo not in seen_server_ports:
                seen_server_ports.add(combo)
                candidate_list.append({
                    'proxy': copy.deepcopy(old_proxy), 'old_name': old_proxy['name'],
                    'dc_base': 'Unknown', 'country': 'UN', 'num': 0, 'port': port
                })

    print(f"Starting Single-Source Standard Test for {len(candidate_list)} generated nodes...")
    
    tested_cands = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(test_candidate, cand) for cand in candidate_list]
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            res = future.result()
            tested_cands.append(res)
            if res['status'] == 'LIVE':
                print(f"[{i}/{len(candidate_list)}] 🟢 LIVE: {res['proxy']['server']}:{res['port']} | {res['speed']} Mbps")
            else:
                pass # برای خلوت شدن لاگ، مرده‌ها را چاپ نمی‌کنیم

    tested_cands.sort(key=lambda x: x['speed'], reverse=True)
    
    live_proxies = []
    live_name_mapping = defaultdict(list)
    all_proxies = []
    all_name_mapping = defaultdict(list)
    
    for cand in tested_cands:
        flag = FLAGS.get(cand['country'], "🏳️")
        dc_title = cand['dc_base'].replace('-', ' ').title()
        base_title = f"{dc_title} {cand['num']}" if cand['num'] > 0 else cand['proxy']['server']
        
        if cand['status'] == 'LIVE':
            new_name = f"[{flag}] {cand['country']} - {base_title}:{cand['port']} - {cand['speed']}Mbps"
            cand['proxy']['name'] = new_name
            live_proxies.append(cand['proxy'])
            live_name_mapping[cand['old_name']].append(new_name)
            all_proxies.append(copy.deepcopy(cand['proxy']))
            all_name_mapping[cand['old_name']].append(new_name)
        else:
            new_name = f"[🔴] {cand['country']} - {base_title}:{cand['port']} - DEAD ({cand.get('error', 'Unknown')})"
            cand['proxy']['name'] = new_name
            all_proxies.append(copy.deepcopy(cand['proxy']))
            all_name_mapping[cand['old_name']].append(new_name)

    print(f"\n======================================")
    print(f"Scan Completed: {len(live_proxies)} LIVE | {len(all_proxies) - len(live_proxies)} DEAD")

    # ذخیره فایل tested.yaml
    tested_clash_data = copy.deepcopy(base_clash_data)
    tested_clash_data['proxies'] = live_proxies
    tested_clash_data = rebuild_clash_groups(tested_clash_data, live_name_mapping, original_proxy_names)
    with open('tested.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(tested_clash_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        
    # ذخیره فایل all.yaml
    all_clash_data = copy.deepcopy(base_clash_data)
    all_clash_data['proxies'] = all_proxies
    all_clash_data = rebuild_clash_groups(all_clash_data, all_name_mapping, original_proxy_names)
    with open('all.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(all_clash_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    # ساخت فایل سینگ‌باکس Karing (فقط با سرورهای زنده)
    generate_singbox_config(live_proxies, "tested-singbox.json")

    print("Success! Saved as `tested.yaml`, `all.yaml`, and `tested-singbox.json`.")

if __name__ == "__main__":
    main()
