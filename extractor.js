const fs = require('fs');

const TOKEN = process.env.VEEPN_TOKEN;
if (!TOKEN) throw new Error("VEEPN_TOKEN ست نشده");

const DOMAINS = [
  "https://freloop.com",
  "https://hibchr.com",
  "https://hisball.com",
  "https://tronlit.com",
  "https://tronyza.com",
  "https://bitphox.com"
];

const REGIONS = [
  "us-va","us-ca","us-ny","us-tx","us-fl","us-il","us-wa","us-nj","us-az","us-co","us-or","us-ga","us-nc","us-mi","us-oh","us-wi","us-ma","us-hi",
  "ca-on","ca-bc","ca-qc","gb-lnd","gb-man","fr-prs","de-ffm","de-ber","nl","ch","se","no","dk","fi","pl","ro","it-mil","it-rome","es","at","be","ie","cz","pt","ua-kv","ru-msk","ru-spb","au-nsw","au-vic","au-qld","nz","sg","jp","in-dl","hk","kr","tw","tr","ae","il","za","br","ar","mx",
  "streaming-us","streaming-gb","streaming-de","streaming-fr","streaming-au","streaming-it","streaming-jp","netflix-us","netflix-uk","bbc-iplayer","hbo-max-us","disney-plus-us","amazon-prime-us"
];

const CONCURRENCY = 15; // تعداد درخواست موازی - بیشتر از 20 نذار بن میشی

async function fetchRegion(region) {
  for (const domain of DOMAINS) {
    try {
      const res = await fetch(`${domain}/api/server/list/`, {
        method: "POST",
        headers: { "accept":"application/json","content-type":"application/json","authorization":`Bearer ${TOKEN}` },
        body: JSON.stringify({ protocol: "https", region, type: 0 })
      });
      if (res.ok) {
        const j = await res.json();
        if (j?.data?.length) return j.data;
      }
    } catch(e){}
  }
  return [];
}

(async () => {
  console.log(`Starting with ${CONCURRENCY} parallel workers...`);
  let allLines = [];
  let total = 0;
  let index = 0;

  async function worker(id) {
    while (true) {
      const i = index++;
      if (i >= REGIONS.length) break;
      const region = REGIONS[i];
      const servers = await fetchRegion(region);
      if (servers.length) {
        console.log(`[Worker ${id}] ${region}: ${servers.length}`);
        servers.forEach((s, idx) => {
          const name = `${s.regionDescription || region} - ${idx+1}`.replace(/"/g,'');
          allLines.push(`  - name: "${name}"\n    type: http\n    server: ${s.addresses[0]}\n    port: ${s.port}\n    username: "${s.username}"\n    password: "${s.password}"\n    tls: true`);
          total++;
        });
      }
    }
  }

  // 15 تا ورکر موازی
  await Promise.all(Array.from({length: CONCURRENCY}, (_, i) => worker(i+1)));

  const output = ["# VeePN Full List", `# Updated: ${new Date().toISOString()}`, `# Total: ${total}`, "proxies:", ...allLines].join("\n");
  fs.writeFileSync("sub", output, "utf8");
  console.log(`\nDONE: ${total} configs -> sub`);
})();
