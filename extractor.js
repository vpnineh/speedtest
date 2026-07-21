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
  "ca-on","ca-bc","ca-qc","gb-lnd","gb-man","fr-prs","de-ffm","de-ber","de-ddf","nl","ch","se","no","dk","fi","pl","ro","it-mil","it-rome","es","at","be","ie","cz","pt","ua-kv","ru-msk","ru-spb","au-nsw","au-vic","au-qld","au-wa","au-sa","nz","sg","jp","in-dl","in-ka","in-mh-mb","hk","kr","tw","th","tr","ae","il","za","br","ar","mx","myanmar","nepal","my","lv","lt","ee","lu","is","hu","bg","gr","hr","cy-nic","md","rs","sk","si","al","dz-algeria","eg","ke","ng","ma-morocco","sa-riyadh","qa","ae","kz","ge","am","az","ba",
  "streaming-us","streaming-gb","streaming-de","streaming-fr","streaming-au","streaming-it","streaming-jp","streaming-nl","streaming-no","streaming-es","streaming-fi","streaming-sg","streaming-in",
  "netflix-us","netflix-uk","netflix-de","netflix-fr","netflix-au","netflix-it","netflix-jp","netflix-nl","netflix-es","netflix-in","netflix-sg","bbc-iplayer","hbo-max-us","hbo-max-es","hbo-max-fi","hbo-max-no","disney-plus-us","amazon-prime-us","amazon-prime-uk","amazon-prime-de","amazon-prime-fr","amazon-prime-it","amazon-prime-jp","dazn-us","dazn-de","dazn-it","hulu-us","paramount-us","fox-us","fubo-us","sling-tv","vix-us","espn-plus","itvx-uk","channel4","channel5","canal-plus-fr","raiplay"
];

(async () => {
  let lines = [];
  lines.push("# VeePN Full List");
  lines.push(`# Updated: ${new Date().toISOString()}`);
  lines.push("proxies:");
  let total = 0;

  for (let i = 0; i < REGIONS.length; i++) {
    const region = REGIONS[i];
    console.log(`[${i+1}/${REGIONS.length}] ${region}`);
    let data = null;

    for (const domain of DOMAINS) {
      try {
        const res = await fetch(`${domain}/api/server/list/`, {
          method: "POST",
          headers: { "accept":"application/json","content-type":"application/json","authorization":"Bearer "+TOKEN },
          body: JSON.stringify({ protocol: "https", region, type: 0 })
        });
        if (res.ok) {
          const j = await res.json();
          if (j?.data?.length) { data = j.data; break; }
        }
      } catch(e){}
    }

    if (data) {
      data.forEach((s, idx) => {
        // یوزر پس مخصوص هر سرور
        const name = `${s.regionDescription || region} - ${idx+1}`.replace(/"/g,'');
        lines.push(`  - name: "${name}"\n    type: http\n    server: ${s.addresses[0]}\n    port: ${s.port}\n    username: "${s.username}"\n    password: "${s.password}"\n    tls: true`);
        total++;
      });
    }
    await new Promise(r => setTimeout(r, 300));
  }

  const output = lines.join("\n");
  fs.writeFileSync("sub", output, "utf8");
  console.log(`\nDONE: ${total} configs -> file sub`);
})();
