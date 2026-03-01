import json, re, itertools, sys
from datetime import datetime
from pathlib import Path

STOP = {
  "the","and","or","of","to","in","for","on","with","a","an","by","from","as","at","is","are",
  "this","that","these","those","we","our","their","its","into","via","using","use","based"
}

def toks(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\\s]", " ", s)
    return [w for w in s.split() if len(w) > 2 and w not in STOP]

def first(o, keys, default=None):
    for k in keys:
        v = o.get(k)
        if v not in (None, "", []):
            return v
    return default

def parse_date(v):
    if not v:
        return None
    if isinstance(v, (int, float)):
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z",""))
    except Exception:
        return None

def opp_title(opp):
    return first(opp, ["opportunity_title","OpportunityTitle","title","OpportunityTitleText"], "")

def opp_number(opp):
    return first(opp, ["opportunity_number","OpportunityNumber","number","OpportunityNumberText"], "")

def opp_id(opp):
    return first(opp, ["opportunity_id","OpportunityID","id","OpportunityId"], "")

def opp_agency(opp):
    return first(opp, ["agency","AgencyCode","agency_code","AgencyName","Agency"], "")

def opp_synopsis(opp):
    return first(opp, ["synopsis","SynopsisDesc","summary","description","OpportunityDescription","synopsis_desc"], "")

def opp_dates(opp):
    posted = first(opp, ["posted_date","PostDate","PostedDate","post_date","OpportunityPostedDate"], None)
    close = first(opp, ["close_date","CloseDate","ApplicationDueDate","due_date","OpportunityCloseDate"], None)
    return parse_date(posted), parse_date(close)

def faculty_text(f):
    return " ".join([
        f.get("name",""),
        f.get("title",""),
        f.get("summary",""),
        " ".join(f.get("keywords", [])) if isinstance(f.get("keywords"), list) else "",
        f.get("search_text","")
    ]).strip()

def overlap_terms(fac, opp):
    fs = set(toks(faculty_text(fac)))
    os = set(toks(" ".join([opp_title(opp), opp_agency(opp), opp_synopsis(opp)])))
    return sorted(list(fs & os))[:12]

def score(fac, opp):
    return float(len(overlap_terms(fac, opp)))

def pick_pairs(ranked, k=5):
    pairs = []
    used = set()
    for a,b in itertools.combinations(ranked, 2):
        if len(pairs) >= k:
            break
        if a.get("id") in used or b.get("id") in used:
            continue
        pairs.append((a,b))
        used.add(a.get("id")); used.add(b.get("id"))
    return pairs

def pick_teams(ranked, k=5):
    teams = []
    i = 0
    while len(teams) < k and i < len(ranked):
        size = 3 + (len(teams) % 3)
        team = ranked[i:i+size]
        if len(team) < 3:
            break
        teams.append(team)
        i += max(2, size-1)
    return teams

def main():
    if len(sys.argv) != 4:
        print("usage: generate_teams.py DEPT_LABEL MAX_OPPS TOP_N")
        print("expects: data/faculty_index.json data/opportunities.json writes data/teams.json")
        sys.exit(2)

    dept = sys.argv[1]
    max_opps = int(sys.argv[2])
    top_n = int(sys.argv[3])

    faculty = json.load(open("data/faculty_index.json"))
    opps_all = json.load(open("data/opportunities.json"))

    decorated = []
    for o in opps_all:
        posted, close = opp_dates(o)
        keydate = close or posted or datetime(1900,1,1)
        decorated.append((keydate, o))
    decorated.sort(key=lambda x: x[0], reverse=True)
    opps = [o for _,o in decorated[:max_opps]]

    out = []
    for opp in opps:
        scored = [(score(f, opp), f) for f in faculty]
        scored.sort(key=lambda x: x[0], reverse=True)

        top = [f for s,f in scored if s > 0][:top_n]
        if len(top) < 6:
            top = [f for s,f in scored][:min(top_n, len(faculty))]

        pairs = pick_pairs(top, 5)
        teams = pick_teams(top, 5)

        t = opp_title(opp) or "Untitled opportunity"
        n = opp_number(opp)
        i = opp_id(opp)

        for a,b in pairs:
            terms = sorted(list(dict.fromkeys(overlap_terms(a, opp) + overlap_terms(b, opp))))
            out.append({
                "team_type": "pair",
                "team_name": f"{dept} pair: {a.get('name','')} + {b.get('name','')}",
                "opportunity_id": i,
                "opportunity_number": n,
                "opportunity_title": t,
                "members": [a.get("name",""), b.get("name","")],
                "member_ids": [a.get("id",""), b.get("id","")],
                "rationale": ("Shared terms: " + ", ".join(terms)) if terms else "Low lexical overlap; plausible conceptual fit based on general scope.",
                "suggested_specific_aim": "Define a focused pilot that ties the opportunity deliverable to an existing departmental strength and a measurable endpoint.",
                "next_steps": "Confirm eligibility and scope, assign a lead, draft a one page concept, and map resources and preliminary data needs.",
                "confidence": "medium"
            })

        for team in teams:
            names = [m.get("name","") for m in team]
            ids = [m.get("id","") for m in team]
            out.append({
                "team_type": "team",
                "team_name": f"{dept} team: " + ", ".join(names[:2]) + (" et al" if len(names) > 2 else ""),
                "opportunity_id": i,
                "opportunity_number": n,
                "opportunity_title": t,
                "members": names,
                "member_ids": ids,
                "rationale": "Team spans complementary expertise aligned to the opportunity scope based on summary keyword overlap.",
                "suggested_specific_aim": "Propose an integrated workflow where each member owns a module contributing to one coherent milestone driven plan.",
                "next_steps": "Hold a 30 minute scoping call, align roles to milestones, identify data gaps, and draft an outline plus budget sketch.",
                "confidence": "medium"
            })

    Path("data").mkdir(parents=True, exist_ok=True)
    with open("data/teams.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("faculty", len(faculty))
    print("opps_used", len(opps))
    print("teams_written", len(out))

if __name__ == "__main__":
    main()
