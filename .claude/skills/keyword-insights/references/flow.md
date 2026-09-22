# The whole flow

Three views of the same machine. The first is what happens end to end; the
second is the graph search that decides what to buy; the third is the
network, which is reported beside the insights.

Every node is coloured by **who does the work**, because that division is
the method:

- **orange — the paid API.** DataForSEO, and nothing else. A keyword call
  is about $0.09 whether it carries one keyword or a thousand; a first page
  of Google is $0.002; Labs difficulty is billed per search.
- **blue — Jev.** Every judgment. No language model appears anywhere.
- **green — code.** Arithmetic, string handling, budgets, and rendering
  sentences from templates. No judgment.

---

## 1. End to end

```mermaid
flowchart TB
  IN(["keyword · country · who is asking"]):::io

  IN --> SERP
  SERP["search results for the seed<br/>who actually ranks"]:::money
  SERP --> QSELL{{"what kind of organisation is this?<br/>sells it · sells something wider ·<br/>lists it · writes about it · buys it"}}:::jev
  QSELL -->|"a focused seller"| SITE
  QSELL -->|"nobody sells here —<br/>itself the finding"| EXPAND

  subgraph OBS["COLLECT — the keyword calls"]
    direction LR
    SITE["for-site<br/>a live business's whole footprint<br/>619 rows where a word gave 31"]:::money
    EXPAND["expand the seed<br/>Google's idea list for a string<br/>collapses on a niche seed"]:::money
    EXPANDP["expand the top of the stack<br/>Google's ideas around the twenty<br/>searches worth most not yet explored"]:::money
    FCAST["forecast<br/>what the biddable searches deliver"]:::money
  end

  SITE --> QREL{{"is this search about what<br/>this market deals in?<br/>every door in, not just harvests"}}:::jev
  EXPAND --> QREL
  EXPANDP --> QREL
  QREL -->|"no, or never asked"| DROPPED["discarded before it can<br/>outvote the market's own words<br/>an unvetted row is not evidence"]:::code
  QREL -->|"yes"| OUTV{"larger than the rest<br/>of the market combined?"}:::code
  OUTV -->|"no"| HEAD
  OUTV -->|"yes"| QOUT{{"stated in words: do most people<br/>typing it mean this market?"}}:::jev
  QOUT -->|"yes: its own head term"| HEAD
  QOUT -->|"no: drawings, 1.83M a month"| DROPPED
  HEAD{"among the market's largest searches,<br/>or the top of the stack?"}:::code
  HEAD -->|"no"| ROWS
  HEAD -->|"yes"| PAGE["page one<br/>$0.002 a search, eight at a time"]:::money
  PAGE --> QGROUND{{"judging by what Google shows,<br/>is this search about this market?"}}:::jev
  QGROUND -->|"yes"| ROWS
  QGROUND -->|"no: top modelling, civil3d"| DROPPED
  ROWS["rows: volume · click price · bids · 48-month series"]:::code
  ROWS --> ADDR["add_rows<br/>collapse word-order permutations<br/>and Google's close variants"]:::code
  ADDR --> GRAPH[("keyword graph")]:::code

  GRAPH --> MINE["mine n-grams and entity candidates<br/>volume-weighted, seen in 2+ keywords"]:::code
  MINE --> QPHRASE{{"a thing, a qualifier, or noise?<br/>is this word a company?"}}:::jev
  QPHRASE --> TOPICS["topics, minus brands and fragments"]:::code

  GRAPH --> CONT["containment: is the topic literally in the keyword?"]:::code
  CONT -->|"exactly one match"| PLACED["placed for free"]:::code
  CONT -->|"none, or several"| QTOPIC{{"which is this search about?"}}:::jev
  TOPICS --> CONT
  GRAPH --> QJOB{{"what is this person trying to do?<br/>8 fixed options"}}:::jev
  GRAPH --> QOFF{{"what kind of answer would satisfy them?<br/>service · software · product · information"}}:::jev
  GRAPH --> QWHO{{"who are they?<br/>firm · practitioner · learner · consumer"}}:::jev
  GRAPH --> QPOT{{"could a newcomer sell to them?<br/>business potential, 0 to 3"}}:::jev
  QJOB --> DECIS["decisive? winner ≥ 2x runner-up<br/>if not, held out and reported"]:::code
  QOFF --> DECIS
  QWHO --> DECIS
  QTOPIC --> DECIS
  QPOT --> SELL["sellable: more than half<br/>the weight on yes"]:::code
  PLACED --> CELLS
  DECIS --> CELLS[("cells: topic × job,<br/>and rows by offering")]:::code

  CELLS --> STATS["statistics: click price weighted by searching,<br/>branded share, year on year, seasonality, spread"]:::code
  STATS --> READ["readings — state each number plainly"]:::code
  READ --> QOBS{{"is that a lot, for a market?"}}:::jev
  QOBS --> EVID["virtual evidence"]:::code

  QCPT{{"63 CPT rows, one request<br/>cached, so re-inference is free"}}:::jev --> NET
  EVID --> NET[("Bayes net<br/>exact enumeration, 32 states")]:::code
  NET --> VERD["posteriors + attribution:<br/>what moved each conclusion"]:::code

  DECIS --> STACK
  SELL --> STACK[("the stack: sellable buyers, then sellable,<br/>then the rest — the money in the clicks within")]:::code
  STACK -->|"effort left, and the last<br/>step found buyers"| EXPANDP
  STACK -->|"effort spent, or<br/>the trail went cold"| FCAST
  STACK --> READSTACK["what the top holds that the market does not:<br/>the fewest searches carrying half the money,<br/>by kind of answer, who, intent, topic"]:::code
  READSTACK --> QADJ
  CELLS --> GEN["generate every claim the shape permits,<br/>contradictory pairs included, and the contrasts:<br/>the money / growth / open ground is in A, not B.<br/>code checks each premise holds as printed"]:::code
  PAGE --> CLUST["the top of the stack grouped by<br/>three shared top-ten results"]:::code
  CLUST --> QKIND{{"what is each result? specialist ·<br/>household name · directory · article ·<br/>forum or social · off-target"}}:::jev
  QKIND --> SPLIT["clicks split by position;<br/>open value = buyer money × share<br/>on pages not built for it"]:::code
  LABS["Labs difficulty · share of voice"]:::money --> WIN
  SPLIT --> WIN["where to win: start here · open door ·<br/>who answers buyers · lead cost by offering ·<br/>who owns · share of search · switching ·<br/>patterns · new demand"]:::code
  GEN --> QADJ{{"fair reading of the measurements?<br/>which of two accounts?<br/>still true with its subject swapped?<br/>guessable from the name alone?<br/>does it change a decision, by a majority?"}}:::jev
  WIN --> QADJ
  QADJ --> KEPT["survivors"]:::code
  KEPT --> QRANK{{"which would change what they do most?<br/>groups of 8, then the winners"}}:::jev
  QRANK --> FIND["ranked findings"]:::code


  FCAST --> COST["clicks available · what each costs ·<br/>what a budget buys"]:::code
  FIND --> REPORT
  COST --> REPORT
  STACK --> REPORT
  REPORT(["insights.md — the top of the stack, the insights<br/>most valuable first, and what paid search can buy"]):::io
  VERD --> DATA
  GEN --> DATA
  GRAPH --> DATA
  SPLIT --> DATA
  STACK --> DATA
  DATA(["data/ — keywords, the whole stack · offerings · topics ·<br/>opportunities · page one · share of voice · tested ·<br/>series · trail · network · forecast · run"]):::io

  classDef money fill:#fdeae1,stroke:#eb6834,stroke-width:1.5px,color:#4a1d0c;
  classDef jev fill:#e4edfb,stroke:#2a78d6,stroke-width:1.5px,color:#10305c;
  classDef code fill:#dff3e8,stroke:#1baf7a,stroke-width:1.5px,color:#0b3b2a;
  classDef io fill:#f2f1ef,stroke:#898781,stroke-width:1.5px,color:#2b2a27;
```

---

## 2. The graph search

Best-first over the stack. Every search is placed on every column and
ranked; the top of the stack not yet explored is expanded — Google's own
ideas around the twenty searches worth most, one call — and what comes back
is vetted, grounded, placed and ranked again. It stops when effort is spent
or when the best of what is left brings back nothing a newcomer could sell
to. Nothing chooses the next step but the stack itself.

```mermaid
stateDiagram-v2
    [*] --> COLLECT
    COLLECT: COLLECT
    COLLECT: harvest who ranks · the seed's ideas
    VET: VET
    VET: in this market? read against page one for the largest
    PLACE: PLACE
    PLACE: every search, every column
    RANK: RANK
    RANK: the stack — sellable buyers, sellable, the rest; money within
    EXPAND: EXPAND
    EXPAND: the top twenty not yet explored, one call
    READ: READ
    READ: page one for the top · where to win · the insights, tested
    PRICE: PRICE
    PRICE: what reaching the buyers costs
    REPORT: REPORT

    COLLECT --> VET
    VET --> PLACE
    PLACE --> RANK
    RANK --> EXPAND: effort left, and the last step found buyers
    EXPAND --> VET
    RANK --> READ: effort spent, or the trail went cold
    READ --> PRICE
    PRICE --> REPORT
    REPORT --> [*]
```

---

## 3. The network

Latent properties are what a reader wants to know and no instrument
measures. Observed nodes are what keyword data sees. Decisions hang at the
bottom, which is why nothing depends on them.

Every table row is one Jev question — *"given that people here will pay and
the words do not reveal intent, can search ads pay for themselves?"* — and
all 63 fit in one request. The structure was audited rather than assumed:
asked which property each measurement is evidence about, Jev agreed with six
of eight hand-drawn edges and corrected two, both correctly, for $0.000078.

```mermaid
flowchart LR
  DEM(["people here will pay<br/>someone to solve this"]):::lat
  LEG(["the words usually reveal<br/>what they want"]):::lat
  OPEN(["buyers have not settled<br/>on who supplies this"]):::lat
  FREE(["many solve it themselves<br/>for free"]):::lat
  GROW(["more search for this<br/>than a year ago"]):::lat

  MON["advertisers pay more<br/>than in a typical market"]:::obs
  CRO["more advertisers compete<br/>than is typical"]:::obs
  BRA["the searches name<br/>particular companies"]:::obs
  DIY["the searches look for<br/>free or manual routes"]:::obs
  VAG["the biggest terms do not<br/>reveal intent"]:::obs
  UPP["more searching than<br/>a year ago"]:::obs
  SPR["searching spreads across<br/>many distinct terms"]:::obs
  GRA["narrowing changes the<br/>click price sharply"]:::obs

  DEM --> MON
  DEM --> CRO
  OPEN --> BRA
  LEG --> BRA
  LEG --> VAG
  LEG --> GRA
  OPEN --> SPR
  FREE --> DIY
  GROW --> UPP

  DEM --> PAID
  LEG --> PAID
  OPEN --> PAID
  FREE --> PAID
  GROW --> PAID
  OPEN --> INC
  DEM --> INC
  FREE --> INC

  PAID(["search ads can<br/>pay for themselves"]):::dec
  INC(["entering means taking from<br/>established names"]):::dec

  classDef lat fill:#e4edfb,stroke:#2a78d6,stroke-width:1.5px,color:#10305c;
  classDef obs fill:#dff3e8,stroke:#1baf7a,stroke-width:1.5px,color:#0b3b2a;
  classDef dec fill:#fdeae1,stroke:#eb6834,stroke-width:2px,color:#4a1d0c;
```

Measurements enter as **virtual evidence** rather than as true or false,
because "0.8 sure this is an expensive market" is the honest input and
forcing it through a threshold would put an invented constant back into the
method. Inference enumerates the five latent roots — thirty-two states —
exactly, in pure Python.
