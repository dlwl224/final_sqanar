# feature_crawler.py

import csv
import requests
from bs4 import BeautifulSoup

from urlbert.urlbert2.core.net_safety import safe_get
from urllib.parse import urlparse, urljoin
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
import os

def is_external(base_domain, link):
    try:
        parsed_link = urlparse(link)
        return parsed_link.netloc and base_domain not in parsed_link.netloc
    except:
        return False

def is_invalid_href(href):
    return not href or href.strip() in ['#', 'javascript:void(0)', 'javascript:;']

def analyze_url_entry(row):
    """
    기존의 batch 처리용 함수.
    row: {'url': ...}
    내부에서 requests.get() 으로 페이지를 가져와 분석한 뒤
    row 에 extUrlRatio, externalAnchorRatio, invalidAnchorRatio 를 붙여서 반환합니다.
    """
    url = row['url']
    try:
        # SSRF 방지: 공인 IP로만 접속하고, 리다이렉트도 단계마다 검사
        response = safe_get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        base_domain = urlparse(url).netloc

        # 외부 리소스 분석
        external_resources = 0
        total_resources = 0

        for script in soup.find_all('script', src=True):
            total_resources += 1
            if is_external(base_domain, script['src']):
                external_resources += 1
        for link in soup.find_all('link', href=True):
            total_resources += 1
            if is_external(base_domain, link['href']):
                external_resources += 1

        ext_url_ratio = external_resources / total_resources if total_resources else 0

        # 앵커 태그 분석
        anchor_tags = soup.find_all('a')
        total_anchors = len(anchor_tags)
        external_anchors = 0
        invalid_anchors = 0

        for a in anchor_tags:
            href = a.get('href')
            if is_invalid_href(href):
                invalid_anchors += 1
            elif is_external(base_domain, urljoin(url, href)):
                external_anchors += 1

        external_anchor_ratio = external_anchors / total_anchors if total_anchors else 0
        invalid_anchor_ratio = invalid_anchors / total_anchors if total_anchors else 0

        row.update({
            'extUrlRatio':         round(ext_url_ratio, 3),
            'externalAnchorRatio': round(external_anchor_ratio, 3),
            'invalidAnchorRatio':  round(invalid_anchor_ratio, 3)
        })

    except Exception as e:
        print(f"Error processing {url}: {e}")
        row.update({
            'extUrlRatio':         None,
            'externalAnchorRatio': None,
            'invalidAnchorRatio':  None
        })

    return row

def extract_crawler_features(url: str) -> dict:
    """
    단일 URL 하나만 넘겨주면,
    extUrlRatio, externalAnchorRatio, invalidAnchorRatio
    세 가지를 dict 로 반환합니다.
    """
    row = {'url': url}
    out = analyze_url_entry(row)
    return {
        'extUrlRatio':         out.get('extUrlRatio')         or 0.0,
        'externalAnchorRatio': out.get('externalAnchorRatio') or 0.0,
        'invalidAnchorRatio':  out.get('invalidAnchorRatio')  or 0.0,
    }

if __name__ == '__main__':
    # 기존에 배치 처리하던 스크립트
    input_file = '/path/to/your/final_whois.csv'
    output_file = '/path/to/your/analyzed_url.csv'

    with open(input_file, newline='', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        all_rows = list(reader)
        fieldnames = reader.fieldnames + [
            'extUrlRatio', 'externalAnchorRatio', 'invalidAnchorRatio'
        ]

    try:
        with open(output_file, newline='', encoding='utf-8') as f:
            existing = {r['url'] for r in csv.DictReader(f)}
    except FileNotFoundError:
        existing = set()

    to_analyze = [r for r in all_rows if r['url'] not in existing]
    print(f"🔍 {len(to_analyze)} URLs to analyze (skipping {len(existing)} already done)")

    with Pool(processes=cpu_count()) as pool:
        results = list(tqdm(pool.imap(analyze_url_entry, to_analyze), total=len(to_analyze)))

    file_exists = os.path.exists(output_file)
    with open(output_file, 'a', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(results)

    print("✅ Batch analysis complete!")
