#!/usr/bin/env bash
# NEXUS interactive setup wizard + launcher.
# Phase 1 — collect all API keys (re-run safe: skips already-set keys)
# Phase 2 — automated infra setup (postgres, migrations, agent registration)
# Phase 3 — docker build + launch
set -euo pipefail

# ── Helpers ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

info()    { echo -e "  ${CYAN}▶${NC}  $*"; }
success() { echo -e "  ${GREEN}✓${NC}  $*"; }
warn()    { echo -e "  ${YELLOW}!${NC}  $*"; }
die()     { echo -e "\n  ${RED}✗  $*${NC}\n" >&2; exit 1; }
header()  { echo -e "\n${BOLD}$*${NC}"; echo -e "${DIM}$(printf '%.0s─' {1..50})${NC}"; }
skip()    { echo -e "  ${DIM}↷  $* (already set)${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
[ -f "docker-compose.yml" ] || die "Run from the nexus/ directory."

# ── Read / write .env ─────────────────────────────────────────────────────────
get_env() {
    grep "^${1}=" .env 2>/dev/null | cut -d= -f2- | head -1
}

set_env() {
    # Writes KEY=VALUE to .env, updating existing line or appending
    python3 -c "
import re, sys
key, val = sys.argv[1], sys.argv[2]
with open('.env', 'r') as f:
    content = f.read()
pattern = r'^' + re.escape(key) + r'=.*$'
replacement = key + '=' + val
if re.search(pattern, content, re.MULTILINE):
    content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
else:
    content = content.rstrip('\n') + '\n' + replacement + '\n'
with open('.env', 'w') as f:
    f.write(content)
" "$1" "$2"
}

is_set() {
    local val
    val=$(get_env "$1")
    case "$val" in
        ""|"your-switch-registration-key-here"|"sk-ant-your-key-here" \
        |"change-me-in-production"|"your-secret-master-key-here" \
        |"your-serpapi-key-here"|"your-blog-api-token")
            return 1 ;;
        *) return 0 ;;
    esac
}

prompt() {
    # prompt KEY "Label" "hint"
    local key="$1" label="$2" hint="${3:-}"
    if is_set "$key"; then
        skip "$label"
        return
    fi
    [ -n "$hint" ] && echo -e "    ${DIM}→ $hint${NC}"
    local val=""
    while [ -z "$val" ]; do
        read -rp "    $label: " val || true
        val="${val// /}"  # strip spaces
    done
    set_env "$key" "$val"
    success "$label saved."
}

prompt_optional() {
    # prompt_optional KEY "Label" "hint" — allows blank input
    local key="$1" label="$2" hint="${3:-}"
    if is_set "$key"; then
        skip "$label"
        return
    fi
    [ -n "$hint" ] && echo -e "    ${DIM}→ $hint${NC}"
    read -rp "    $label (blank to skip): " val || true
    val="${val// /}"
    if [ -n "$val" ]; then
        set_env "$key" "$val"
        success "$label saved."
    else
        warn "$label skipped — mock/fallback mode will be used."
    fi
}

# ── Banner ────────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "${BOLD}╔════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║        NEXUS  —  Setup Wizard          ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════╝${NC}"
echo ""

# ── Prerequisites ─────────────────────────────────────────────────────────────
header "[0/3]  Checking prerequisites"

command -v docker &>/dev/null    || die "Docker not found → https://docs.docker.com/get-docker/"
docker compose version &>/dev/null 2>&1 || die "Docker Compose v2 not found. Update Docker Desktop."
command -v python3 &>/dev/null   || die "Python 3.11+ not found."
PY_OK=$(python3 -c "import sys; print(sys.version_info >= (3,11))" 2>/dev/null || echo False)
[ "$PY_OK" = "True" ] || die "Python 3.11+ required. Got: $(python3 --version 2>&1)"

success "Docker OK"
success "Python OK"

[ -f ".env" ] || cp .env.example .env && success "Created .env"

# ══════════════════════════════════════════════════════════════════════════════
header "[1/3]  Collecting API keys"
echo -e "  ${DIM}Already-set values are skipped automatically.${NC}"
echo -e "  ${DIM}Press Ctrl+C at any time — re-running resumes where you left off.${NC}"

# ── Switch ────────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}SWITCH PLATFORM${NC}"

# Ask local vs hosted
SWITCH_URL=$(get_env "SWITCH_SERVER_URL")
if [ -z "$SWITCH_URL" ] || [ "$SWITCH_URL" = "http://localhost:8080" ]; then

    echo ""
    echo -e "  ${YELLOW}Is Switch running locally (Docker) or hosted?${NC}"
    echo "    1) Local Docker  (we'll start it for you)"
    echo "    2) Hosted / already running"
    read -rp "  Choose [1/2]: " switch_choice || switch_choice="1"

    if [ "${switch_choice}" = "2" ]; then
        read -rp "    Switch URL (e.g. https://myswitch.example.com): " sw_url || sw_url=""
        sw_url="${sw_url// /}"
        [ -n "$sw_url" ] && set_env "SWITCH_SERVER_URL" "$sw_url"
    else
        set_env "SWITCH_SERVER_URL" "http://localhost:8080"
        # Start Switch if not already running
        if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "switch"; then
            info "Starting Switch container..."
            docker run -d -p 8080:8080 --name switch fliptheswitch/switch:latest \
                >/dev/null 2>&1 || warn "Switch may already exist — skipping start."
            info "Waiting for Switch to be ready..."
            for i in {1..20}; do
                curl -sf http://localhost:8080/health &>/dev/null && break
                sleep 2
            done
        fi
        success "Switch running at http://localhost:8080"
    fi
fi

# Guide room creation
ROOMS_SET=true
for room_var in SALES SUPPORT CS FINANCE GROWTH CONTENT DEVOPS; do
    is_set "SWITCH_ROOM_ID_${room_var}" || { ROOMS_SET=false; break; }
done

if [ "$ROOMS_SET" = "false" ]; then
    SW_URL=$(get_env "SWITCH_SERVER_URL")
    echo ""
    echo -e "  ${YELLOW}You need to create 7 rooms in the Switch Console.${NC}"
    echo -e "  ${BOLD}  Open: ${SW_URL}${NC}  (or your hosted URL)"
    echo ""
    echo "  Create these rooms (exact names matter):"
    echo "    nexus-sales    nexus-support   nexus-cs"
    echo "    nexus-finance  nexus-growth    nexus-content   nexus-devops"
    echo ""
    echo "  Also copy the Registration Key from: Console → Settings → Registration Key"
    echo ""
    read -rp "  Press ENTER when rooms are created... " _ || true
fi

echo ""
prompt "SWITCH_REGISTRATION_KEY" \
    "Switch Registration Key" \
    "Switch Console → Settings → Registration Key"

echo ""
echo -e "  ${DIM}Now copy each Room ID from Switch Console → Rooms → <room name>${NC}"
echo ""

prompt "SWITCH_ROOM_ID_SALES"    "Room ID for  nexus-sales"
prompt "SWITCH_ROOM_ID_SUPPORT"  "Room ID for  nexus-support"
prompt "SWITCH_ROOM_ID_CS"       "Room ID for  nexus-cs"
prompt "SWITCH_ROOM_ID_FINANCE"  "Room ID for  nexus-finance"
prompt "SWITCH_ROOM_ID_GROWTH"   "Room ID for  nexus-growth"
prompt "SWITCH_ROOM_ID_CONTENT"  "Room ID for  nexus-content"
prompt "SWITCH_ROOM_ID_DEVOPS"   "Room ID for  nexus-devops"

# ── Anthropic ─────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}ANTHROPIC  (Claude AI — powers all agents)${NC}"
echo ""
prompt "ANTHROPIC_API_KEY" \
    "Anthropic API key  (sk-ant-...)" \
    "console.anthropic.com → API Keys → Create Key → copy the sk-ant-... value"

# ── NEXUS Master Key (auto-generate) ─────────────────────────────────────────
echo ""
echo -e "  ${BOLD}NEXUS MASTER KEY  (management API secret)${NC}"
echo ""
if ! is_set "NEXUS_MASTER_KEY"; then
    generated_key=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    set_env "NEXUS_MASTER_KEY" "$generated_key"
    success "NEXUS_MASTER_KEY auto-generated: ${DIM}${generated_key}${NC}"
    warn "Save this key — you'll need it for management API calls."
else
    skip "NEXUS_MASTER_KEY"
fi

# ── Optional: SerpAPI ─────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}SEO / SERPAPI  ${DIM}(optional — mock mode is fine for demo)${NC}"
echo ""
read -rp "  Set up live SerpAPI for real SEO data? [y/N]: " want_seo || want_seo="n"
if [[ "${want_seo,,}" == "y" ]]; then
    prompt_optional "SERPAPI_KEY" \
        "SerpAPI key" \
        "serpapi.com → Dashboard → API Key  (free tier: 100 searches/month)"
    set_env "GEO_SEO_MOCK_MODE" "false"
    success "GEO_SEO_MOCK_MODE set to false."
else
    set_env "GEO_SEO_MOCK_MODE" "true"
    skip "SerpAPI — using mock mode (GEO_SEO_MOCK_MODE=true)"
fi

# ── Optional: Email ───────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}EMAIL ESCALATION  ${DIM}(optional — only needed for real email alerts)${NC}"
echo ""
read -rp "  Set up email for escalation notifications? [y/N]: " want_email || want_email="n"
if [[ "${want_email,,}" == "y" ]]; then
    echo ""
    echo "    Option A: SendGrid (recommended)"
    echo "    Option B: Gmail / SMTP"
    read -rp "  Choose [A/B]: " email_choice || email_choice="A"

    if [[ "${email_choice,,}" == "b" ]]; then
        prompt "SMTP_HOST"     "SMTP host" "e.g. smtp.gmail.com"
        prompt "SMTP_PORT"     "SMTP port" "587 for TLS, 465 for SSL"
        prompt "SMTP_USER"     "SMTP username / email"
        prompt "SMTP_PASSWORD" "SMTP password / app-password" \
            "Gmail: Google Account → Security → App Passwords → create one"
        prompt "EMAIL_FROM"    "From address" "must match SMTP_USER for Gmail"
    else
        prompt "SENDGRID_API_KEY" \
            "SendGrid API key  (SG....)" \
            "app.sendgrid.com → Settings → API Keys → Create API Key"
        prompt "EMAIL_FROM" \
            "From address" \
            "must be a Verified Sender in your SendGrid account"
    fi
fi

# ── Optional: Stripe ─────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}BILLING / STRIPE  ${DIM}(optional — BILLING_MOCK_MODE=true by default)${NC}"
echo ""
read -rp "  Set up Stripe for real billing? [y/N]: " want_stripe || want_stripe="n"
if [[ "${want_stripe,,}" == "y" ]]; then
    echo -e "  ${DIM}→ dashboard.stripe.com → Developers → API keys${NC}"
    prompt "STRIPE_SECRET_KEY" \
        "Stripe secret key  (sk_test_... or sk_live_...)" \
        "Stripe Dashboard → Developers → API keys → Secret key"
    prompt "STRIPE_WEBHOOK_SECRET" \
        "Stripe webhook secret  (whsec_...)" \
        "Stripe Dashboard → Developers → Webhooks → Add endpoint → Signing secret"
    prompt "STRIPE_PRICE_STARTER"    "Price ID — Starter plan  (price_...)" \
        "Stripe Dashboard → Products → create product → copy Price ID"
    prompt "STRIPE_PRICE_PRO"        "Price ID — Pro plan  (price_...)"
    prompt "STRIPE_PRICE_ENTERPRISE" "Price ID — Enterprise plan  (price_...)"
    set_env "BILLING_MOCK_MODE" "false"
    success "BILLING_MOCK_MODE set to false."
else
    set_env "BILLING_MOCK_MODE" "true"
    skip "Stripe — using mock mode (BILLING_MOCK_MODE=true)"
fi

# ── Optional: Blog CMS ────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}BLOG CMS  ${DIM}(optional — BLOG_MOCK_MODE=true by default)${NC}"
echo ""
read -rp "  Connect a real blog CMS? [y/N]: " want_blog || want_blog="n"
if [[ "${want_blog,,}" == "y" ]]; then
    echo "    Adapters: custom | wordpress | ghost"
    prompt "BLOG_API_ADAPTER"  "CMS adapter" "custom | wordpress | ghost"
    prompt "BLOG_API_ENDPOINT" "CMS API endpoint URL" \
        "WordPress: https://yourblog.com/wp-json/wp/v2/posts  |  Ghost: https://yourblog.com/ghost/api/v3/admin/posts"
    prompt "BLOG_API_TOKEN"    "CMS API token" \
        "WordPress: Users → Application Passwords  |  Ghost: Settings → Integrations → Add custom integration"
    set_env "BLOG_MOCK_MODE" "false"
    success "BLOG_MOCK_MODE set to false."
else
    set_env "BLOG_MOCK_MODE" "true"
    skip "Blog CMS — using mock mode (BLOG_MOCK_MODE=true)"
fi

echo ""
echo -e "  ${GREEN}${BOLD}All keys collected!${NC}"

# ══════════════════════════════════════════════════════════════════════════════
header "[2/3]  Setting up infrastructure"

# ── Python deps ───────────────────────────────────────────────────────────────
if ! python3 -c "import anthropic" &>/dev/null 2>&1; then
    info "Installing Python dependencies..."
    pip install -r requirements.txt -q || die "pip install failed. Try: pip3 install -r requirements.txt"
    success "Python dependencies installed."
else
    success "Python dependencies already installed."
fi

# ── PostgreSQL ────────────────────────────────────────────────────────────────
info "Starting PostgreSQL..."
docker compose up postgres -d

info "Waiting for PostgreSQL to be healthy..."
ATTEMPTS=0
until docker compose exec -T postgres pg_isready -U nexus &>/dev/null 2>&1; do
    ATTEMPTS=$((ATTEMPTS + 1))
    [ "$ATTEMPTS" -ge 30 ] && die "PostgreSQL did not become healthy after 60s.\nCheck: docker compose logs postgres"
    sleep 2
done
success "PostgreSQL ready."

# ── Migrations ────────────────────────────────────────────────────────────────
info "Running database migrations..."
python3 artisan.py migrate
success "Migrations complete."

# ── Register agents ───────────────────────────────────────────────────────────
if ! is_set "SWITCH_AGENT_ID_SALES"; then
    info "Registering 7 agents with Switch..."
    python3 artisan.py register-agents
    success "Agents registered — IDs/keys written to .env."
else
    success "Agents already registered. Skipping."
fi

# ── Tenant config ─────────────────────────────────────────────────────────────
info "Ensuring tenant config..."
python3 artisan.py ensure-tenant-config
success "Tenant config OK."

# ── Demo data ─────────────────────────────────────────────────────────────────
echo ""
read -rp "  $(echo -e "${YELLOW}Seed demo data?${NC}") 3 leads, keywords, services [y/N]: " seed_choice || seed_choice="n"
if [[ "${seed_choice,,}" == "y" ]]; then
    info "Seeding demo data..."
    python3 artisan.py seed
    success "Demo data seeded."
fi

# ══════════════════════════════════════════════════════════════════════════════
header "[3/3]  Launching all services"

echo ""
info "Building Docker images and starting all containers..."
echo -e "  ${DIM}(first build may take a few minutes)${NC}"
docker compose up -d --build

echo ""
success "All services started."
echo ""
docker compose ps

# ── Summary ───────────────────────────────────────────────────────────────────
MGMT_PORT=$(get_env "MANAGEMENT_API_PORT"); MGMT_PORT="${MGMT_PORT:-5000}"
VOICE_PORT=$(get_env "VOICE_SERVER_PORT");  VOICE_PORT="${VOICE_PORT:-5001}"
MASTER_KEY=$(get_env "NEXUS_MASTER_KEY")

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║         NEXUS is running!                ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  Management API:  http://localhost:${MGMT_PORT}/api/v1/health"
echo "  Voice server:    http://localhost:${VOICE_PORT}"
echo ""
echo "  Check agent status (run in terminal):"
echo -e "  ${DIM}curl -H \"Authorization: Bearer ${MASTER_KEY}\" \\${NC}"
echo -e "  ${DIM}     http://localhost:${MGMT_PORT}/api/v1/tenants/default/agents/status${NC}"
echo ""
echo "  Useful commands:"
echo "    docker compose logs -f          # tail all logs"
echo "    docker compose logs sales_agent -f   # single agent"
echo "    docker compose down             # stop everything"
echo "    docker compose down -v          # stop + wipe database"
echo "    bash run.sh                     # re-run (safe, skips done steps)"
echo ""
