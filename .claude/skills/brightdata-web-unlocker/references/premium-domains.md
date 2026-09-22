# Premium Web Unlocker domains

Domains that require Bright Data's `web_unlocker_premium` zone instead of
the default `web_unlocker1` zone. `scripts/unlock.py` auto-detects these by
hostname (matching the domain itself or any subdomain of it) — you don't
need to consult this file to use the skill, it's here for quick lookup.

**The authoritative, machine-read copy is `../scripts/premium_domains.py`**
(the `PREMIUM_DOMAINS` set). If you add or remove a domain, edit that file
first and mirror the change here — this file is documentation, not the
source the code runs on.

```
advanceautoparts.com
affitto.it
agoda.cn
albertsons.com
allpeople.com
autozone.com
bestbuy.com
bestwestern.com
billiger.de
bottlerover.com
carousell.com
carousell.com.hk
carousell.com.my
carousell.ph
carousell.sg
carsales.com.au
cdiscount.com
chewy.com
costco.com
cvs.com
despegar.com.mx
dickssportinggoods.com
dynos.es
emaxme.com
familytreenow.com
feuvert.fr
flooranddecor.com
foodlion.com
footlocker.co.uk
footlocker.com
giantfoodstores.com
gopuff.com
gplay.bg
hermes.com
hyatt.com
idealo.de
immobilienscout24.de
ingatlan.com
instacart.com
intersport.fr
joann.com
kroger.com
lazada.co.id
lazada.co.th
lazada.com.my
lazada.com.ph
lazada.sg
lazada.vn
lowes.ca
lowes.com
mcmaster.com
mediamarkt.de
mediamarkt.es
medline.com
mscdirect.com
napaonline.com
nofrills.ca
peoplefinders.com
platt.com
publicdatausa.com
realcanadiansuperstore.ca
realestate.com.au
restaurantguru.com
searchpeoplefree.com
shopee.cl
shopee.co.id
shopee.co.th
shopee.com.br
shopee.com.co
shopee.com.mx
shopee.com.my
shopee.ph
shopee.sg
shopee.tw
shopee.vn
similarweb.com
skyscanner.co.kr
skyscanner.net
stopandshop.com
target.com
temu.com
ticketmaster.com
totalwine.com
tractorsupply.com
walmart.com.mx
wayfair.com
weismarkets.com
wizzair.com
worten.pt
```

89 domains total. Matching is host-suffix aware: `shop.target.com` and
`www.target.com` both match `target.com`; a domain that merely shares a
substring (e.g. `targetcompany.com`) does not.

If a fetch through `web_unlocker1` comes back blocked or challenged for a
domain not listed here, that's the signal Bright Data has moved it into the
premium tier — add it to both files rather than routing around it per-call.
