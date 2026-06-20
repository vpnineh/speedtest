import yaml
import requests
import time
import re
import concurrent.futures
from collections import defaultdict

# دیکشنری پرچم‌ها بر اساس کدهای دوحرفی استخراج شده از دامنه
FLAGS = {
    "US": "🇺🇸", "UK": "🇬🇧", "GB": "🇬🇧", "FR": "🇫🇷", 
    "NL": "🇳🇱", "SG": "🇸🇬", "RU": "🇷🇺", "DE": "🇩🇪"
}

TEST_URL = "http://speed.cloudflare.com/__down?bytes=15000000" # دانلود فایل 15 مگابایتی
TIMEOUT = 10 # حداکثر زمان تست برای هر کانفیگ به ثانیه

def test_candidate(cand):
    """تست سرعت یک کانفیگ منفرد"""
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
        resp = requests.get(TEST_URL, proxies=proxies, timeout=TIMEOUT)
        resp.raise_for_status()
        duration = time.time() - start
        
        # محاسبه دقیق سرعت مگابیت بر ثانیه
        mbps = (len(resp.content) * 8) / duration / 1_000_000
        cand['speed'] = round(mbps, 1)
        return cand
    except Exception:
        cand['speed'] = 0.0 # کانفیگ مرده یا تایم‌اوت شده
        return cand

def main():
    print("Loading vpnlist.yaml...")
    try:
        with open('vpnlist.yaml', 'r', encoding='utf-8') as f:
            clash_data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading yaml: {e}")
        return

    original_proxies = clash_data.get('proxies', [])
    original_proxy_names = {p['name'] for p in original_proxies}
    candidate_list = []
    seen_server_ports = set() # برای جلوگیری از تولید تست‌های تکراری

    print("Offline Parsing: Generating 1 to 10 nodes for each server...")
    
    # ۱. استخراج آفلاین دیتاسنتر/کشور و تولید ۱۰ حالت برای هرکدام
    for old_proxy in original_proxies:
        server = old_proxy.get('server', '')
        port = old_proxy.get('port', 0)
        
        # این رگولار اکسپرشن نام را می‌شکند: مثلا trout-east-4-us را به (trout-east) و (us) تفکیک می‌کند
        match = re.match(r'^([a-zA-Z0-9-]+?)(?:-\d+)?-([a-zA-Z]{2})\.maxxxcdn\.com$', server)
        
        if match:
            dc_base = match.group(1)
            country = match.group(2).upper()
            
            # تولید سرورهای ۱ تا ۱۰
            for i in range(1, 11):
                new_server = f"{dc_base}-{i}-{country.lower()}.maxxxcdn.com"
                combo = f"{new_server}:{port}" # ترکیب یونیک سرور و پورت
                
                if combo in seen_server_ports:
                    continue
                seen_server_ports.add(combo)
                
                new_proxy = old_proxy.copy()
                new_proxy['server'] = new_server
                
                candidate_list.append({
                    'proxy': new_proxy,
                    'old_name': old_proxy['name'],
                    'dc_base': dc_base,
                    'country': country,
                    'num': i,
                    'port': port
                })
        else:
            # اگر فرمت سرور عجیب بود (مثلا آی‌پی مستقیم بود)، فقط خودش را تست کن
            combo = f"{server}:{port}"
            if combo not in seen_server_ports:
                seen_server_ports.add(combo)
                candidate_list.append({
                    'proxy': old_proxy.copy(),
                    'old_name': old_proxy['name'],
                    'dc_base': 'Unknown',
                    'country': 'UN',
                    'num': 0,
                    'port': port
                })

    print(f"Generated {len(candidate_list)} target servers. Starting Deep Speed Test (Multi-Threaded)...")
    
    # ۲. تست سرعت تمام ۴۶۰ سرور به صورت همزمان (۵۰ کانکشن موازی)
    successful_cands = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(test_candidate, cand) for cand in candidate_list]
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            res = future.result()
            if res['speed'] > 0:
                successful_cands.append(res)
                print(f"[{i}/{len(candidate_list)}] 🟢 LIVE: {res['proxy']['server']}:{res['port']} | {res['speed']} Mbps")
            else:
                print(f"[{i}/{len(candidate_list)}] 🔴 DEAD: {res['proxy']['server']}:{res['port']}")

    # ۳. فیلتر کردن، سورت کردن و نام‌گذاری نهایی
    successful_cands.sort(key=lambda x: x['speed'], reverse=True)
    final_proxies = []
    old_name_to_new_names = defaultdict(list)
    
    for cand in successful_cands:
        flag = FLAGS.get(cand['country'], "🏳️")
        # تمیز کردن نام دیتاسنتر (مثلا trout-east میشود Trout East)
        dc_title = cand['dc_base'].replace('-', ' ').title()
        
        if cand['num'] > 0:
            # فرمت نهایی بر اساس درخواست شما (پورت اضافه شد تا کلش کرش نکند)
            new_name = f"[{flag}] {cand['country']} - {dc_title} {cand['num']}:{cand['port']} - {cand['speed']}Mbps"
        else:
            new_name = f"[{flag}] {cand['country']} - {cand['proxy']['server']} - {cand['speed']}Mbps"
        
        cand['proxy']['name'] = new_name
        final_proxies.append(cand['proxy'])
        old_name_to_new_names[cand['old_name']].append(new_name)
        
    clash_data['proxies'] = final_proxies
    print(f"\n======================================")
    print(f"Filtered down to {len(final_proxies)} working proxies.")

    # ۴. تعمیر هوشمند گروه‌ها
    if 'proxy-groups' in clash_data:
        for group in clash_data['proxy-groups']:
            if 'proxies' not in group: continue
            new_group_proxies = []
            for p_name in group['proxies']:
                # اگر نام قبلی متعلق به یک پروکسی بود، لیستی از پروکسی‌های جدید زنده را جایگزین کن
                if p_name in original_proxy_names:
                    new_group_proxies.extend(old_name_to_new_names.get(p_name, []))
                else:
                    # اگر نام متعلق به یک زیرگروه بود (مثلا Auto-US)، آن را نگه دار
                    new_group_proxies.append(p_name)
            
            # حذف موارد تکراری ایجاد شده در گروه ضمن حفظ ترتیب سورت سرعت
            seen = set()
            group['proxies'] = [x for x in new_group_proxies if not (x in seen or seen.add(x))]

    with open('out.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(clash_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        
    print("Process Finished Successfully! Saved to out.yaml")

if __name__ == "__main__":
    main()
