"""
Wipe the database and load reproducible demo data (CRM + catalog).

All seeded business rows use stable UUID v5 identifiers (see novaquote.mdc: stable UUIDs).

Usage:
    python manage.py seed_demo --yes
    python manage.py seed_demo --yes --username admin --password demo

Requires --yes to confirm destructive flush.
"""

from __future__ import annotations

import random
import urllib.request
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone as django_timezone

from pricelist.models import (
    Category,
    Combination,
    CombinationItem,
    ContractDuration,
    Department,
    GeneralSettings,
    Organization,
    OrganizationInvoice,
    OrganizationNetworkLink,
    OrganizationPerson,
    OrganizationRole,
    Person,
    PersonEvent,
    PersonHobby,
    PersonLifeEvent,
    Product,
    ProductOption,
    ProductSupplier,
    ProfitProfile,
    Proposal,
    ProposalContractSnapshot,
    ProposalHistory,
    ProposalLine,
    Order,
    OrderLineItem,
    Supplier,
)
from pricelist.rbac_demo_seed import ensure_frontend_roles_and_demo_users
from pricelist.services.invoice_service import create_invoice_for_proposal, mark_invoice_sent
from pricelist.services.order_service import create_order_from_proposal


User = get_user_model()


# Namespace for deterministic demo UUIDs (novaquote.mdc: stable external references)
_DEMO_NS = uuid.UUID("018f2b7e-8c4d-7a9e-8b0d-111111111101")


def demo_u(key: str) -> uuid.UUID:
    """Stable UUID v5 for seeded rows; same key => same UUID every reseed."""
    return uuid.uuid5(_DEMO_NS, f"novaquote.demo.{key}")

# Reproducible "random" demo data (departments/person counts only)
random.seed(42)

FIRST_NAMES = (
    "Emma",
    "Lucas",
    "Sophie",
    "Daan",
    "Julia",
    "Sem",
    "Eva",
    "Finn",
    "Lotte",
    "Noah",
    "Mila",
    "Thijs",
    "Anna",
    "Bram",
    "Iris",
    "Luuk",
    "Nina",
    "Oscar",
    "Sanne",
    "Tom",
)
LAST_NAMES = (
    "de Vries",
    "Jansen",
    "Bakker",
    "Visser",
    "Smit",
    "Mulder",
    "de Boer",
    "Bos",
    "Vos",
    "Hendriks",
    "van Dijk",
    "Dekker",
    "van den Berg",
    "Jacobs",
    "Willems",
    "Hoekstra",
    "Meijer",
    "Schouten",
    "de Jong",
    "Kuijpers",
)
DEPARTMENT_NAMES = (
    "Finance",
    "Operations",
    "IT",
    "Facilities",
    "HR",
    "Sales",
    "Customer service",
    "Warehouse",
)
JOB_TITLES = (
    "Office Manager",
    "IT Coordinator",
    "Buyer",
    "Facilities Lead",
    "CFO",
    "Operations Director",
    "Reception",
    "Head of Sales",
)
HOBBY_NAMES = (
    "Photography",
    "Cycling",
    "Jazz piano",
    "Trail running",
    "Home roasting coffee",
    "Board games",
    "Volunteer coaching",
    "Urban sketching",
    "Open-source tooling",
    "Sailing",
)
LIFE_EVENT_NOTES = (
    "Sent article on secure print release; positive reply.",
    "Met at channel partner dinner — follow up on MFP fleet audit.",
    "Quick call: expanding Utrecht warehouse, Q3 budget.",
    "Shared case study on pull printing; asked for intro to IT lead.",
)
PLACEHOLDER_IMAGE_URL = "https://placehold.net/600x800.png"


def _download_placeholder_png() -> bytes:
    req = urllib.request.Request(
        PLACEHOLDER_IMAGE_URL,
        headers={"User-Agent": "NovaQuoteSeed/1.0"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()


def _bump_product_cost(product: Product, new_cost: Decimal) -> None:
    """Change cost and mirror preferred ProductSupplier (creates PriceHistory via signal)."""
    product.cost_price = new_cost
    product.save()
    ProductSupplier.objects.filter(product=product, is_preferred=True).update(cost_price=new_cost)


def _attach_demo_images(products: dict[str, Product], combination: Combination | None, stdout) -> None:
    try:
        png = _download_placeholder_png()
    except Exception as exc:
        stdout.write(f"  (Skipping product images: could not download placeholder — {exc})")
        return
    for key, p in products.items():
        if p.image:
            continue
        p.image.save(f"seed-{key}.png", ContentFile(png), save=True)
    if combination and not combination.image:
        combination.image.save("seed-bundle.png", ContentFile(png), save=True)


def _create_organization(
    org_key: str,
    name: str,
    roles: list[str],
    *,
    billing_city: str = "Rotterdam",
    **kwargs,
) -> Organization:
    """Create org with stable UUID and explicit roles (no stray auto-lead)."""
    org = Organization(
        uuid=demo_u(f"organization.{org_key}"),
        name=name,
        billing_line1=f"{random.randint(1, 180)} Demo Lane",
        billing_city=billing_city,
        billing_postal_code=f"{random.randint(1000, 9999)} {random.choice(['AB', 'CD', 'XY'])}",
        billing_country="Netherlands",
        email=kwargs.pop("email", ""),
        phone=f"+31 10 {random.randint(2000000, 7999999)}",
        website=kwargs.pop("website", ""),
        **kwargs,
    )
    if not org.email:
        slug = "".join(c for c in name.lower() if c.isalnum())[:24] or "demo"
        org.email = f"contact@{slug}.demo.local"
    org.save()
    org.role_assignments.all().delete()
    for role in roles:
        OrganizationRole.objects.create(
            uuid=demo_u(f"organizationrole.{org_key}.{role}"),
            organization=org,
            role=role,
        )
    return org


def _add_departments(org: Organization, org_key: str, names: list[str]) -> list[Department]:
    out = []
    for i, dname in enumerate(names):
        out.append(
            Department.objects.create(
                uuid=demo_u(f"department.{org_key}.{dname.lower().replace(' ', '_')}"),
                organization=org,
                name=dname,
                email=f"{dname.lower().replace(' ', '')}@{org.email.split('@')[-1]}",
            )
        )
    return out


_person_seq = 0


def _add_people_and_memberships(
    org: Organization,
    org_key: str,
    departments: list[Department],
    count: int,
) -> list[OrganizationPerson]:
    global _person_seq
    memberships: list[OrganizationPerson] = []
    for _ in range(count):
        _person_seq += 1
        pk = f"{_person_seq:04d}"
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        person = Person.objects.create(
            uuid=demo_u(f"person.{pk}"),
            first_name=fn,
            last_name=ln,
            personal_email=f"{fn.lower()}.{ln.lower().replace(' ', '')}.{pk}@email.demo".replace("..", "."),
        )
        dept = random.choice(departments)
        m = OrganizationPerson.objects.create(
            uuid=demo_u(f"organizationperson.{org_key}.{pk}"),
            organization=org,
            person=person,
            department=dept,
            job_title=random.choice(JOB_TITLES),
            company_email=f"{fn[0].lower()}{ln.lower().replace(' ', '')[:8]}{pk}@{org.email.split('@')[-1]}",
            company_phone=org.phone,
            is_primary_contact=len(memberships) == 0,
        )
        memberships.append(m)
    return memberships


def _pick_department(departments: list[Department], *prefer_names: str) -> Department:
    for name in prefer_names:
        for d in departments:
            if d.name.lower() == name.lower():
                return d
    return departments[0]


class Command(BaseCommand):
    help = "Flush the database and load demo catalog + CRM data (destructive)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirm that you want to erase all data and reseed.",
        )
        parser.add_argument("--username", default="admin", help="Superuser username (default: admin)")
        parser.add_argument("--email", default="admin@demo.local", help="Superuser email")
        parser.add_argument("--password", default="demo", help="Superuser password (default: demo)")

    def handle(self, *args, **options):
        global _person_seq
        _person_seq = 0

        if not options["yes"]:
            raise CommandError("Refusing to run without --yes (this wipes the entire database).")

        username = options["username"]
        email = options["email"]
        password = options["password"]

        self.stdout.write(self.style.WARNING("Flushing database…"))
        call_command("flush", interactive=False, verbosity=0)

        with transaction.atomic():
            User.objects.create_superuser(username=username, email=email, password=password)
            admin_user = User.objects.get(username=username)
            ensure_frontend_roles_and_demo_users(
                password, admin_user=admin_user, reset_demo_passwords=True
            )

            GeneralSettings.objects.create(
                uuid=demo_u("generalsettings.singleton"),
                site_name="NovaQuote",
                currency="EUR",
                rounding="0.01",
                number_format=GeneralSettings.NUMBER_FORMAT_EUROPE,
                language=GeneralSettings.LANGUAGE_EN,
                logo=None,
                time_per_product_minutes=Decimal("15.00"),
                minimum_visit_minutes=Decimal("60.00"),
                hourly_rate=Decimal("75.00"),
                color_scheme=GeneralSettings.COLOR_SCHEME_TEAL,
                primary_color="#008080",
                primary_color_hover="#006666",
            )

            profile = ProfitProfile.objects.create(
                uuid=demo_u("profitprofile.standard_resale"),
                name="Standard resale",
                markup_percentage=Decimal("22.00"),
                markup_fixed=Decimal("0.00"),
                is_active=True,
            )
            profile_ent = ProfitProfile.objects.create(
                uuid=demo_u("profitprofile.enterprise_resale"),
                name="Enterprise resale",
                markup_percentage=Decimal("18.00"),
                markup_fixed=Decimal("25.00"),
                is_active=True,
            )

            categories: dict[str, Category] = {
                "Printers & MFPs": Category.objects.create(
                    uuid=demo_u("category.printers_mfps"),
                    name="Printers & MFPs",
                    sort_order=10,
                ),
                "Scanners": Category.objects.create(
                    uuid=demo_u("category.scanners"),
                    name="Scanners",
                    sort_order=20,
                ),
                "Supplies": Category.objects.create(
                    uuid=demo_u("category.supplies"),
                    name="Supplies",
                    sort_order=30,
                ),
                "Services": Category.objects.create(
                    uuid=demo_u("category.services"),
                    name="Services",
                    sort_order=40,
                ),
            }

            # --- CRM: supplier organizations (Contacts → Suppliers) + catalog Supplier rows ----------
            org_ingram = _create_organization(
                "supplier_ingram",
                "Ingram Micro Benelux B.V.",
                [OrganizationRole.ROLE_SUPPLIER],
                billing_city="Hoofddorp",
                website="https://ingram.demo.local",
                email="nl.orders@ingram.demo.local",
                payment_terms="Net 30",
            )
            depts_ingram = _add_departments(
                org_ingram,
                "supplier_ingram",
                ["Sales", "Distribution", "Credit control"],
            )
            mem_ingram = _add_people_and_memberships(org_ingram, "supplier_ingram", depts_ingram, 4)
            ingram_sales = _pick_department(depts_ingram, "Sales")
            ingram_contact = next((m for m in mem_ingram if m.department_id == ingram_sales.id), mem_ingram[0])

            org_synnex = _create_organization(
                "supplier_synnex",
                "TD SYNNEX Netherlands B.V.",
                [OrganizationRole.ROLE_SUPPLIER],
                billing_city="Amstelveen",
                website="https://tdsynnex.demo.local",
                email="inside.sales@tdsynnex.demo.local",
                payment_terms="Net 45",
            )
            depts_synnex = _add_departments(
                org_synnex,
                "supplier_synnex",
                ["Inside sales", "Logistics", "Vendor management"],
            )
            mem_synnex = _add_people_and_memberships(org_synnex, "supplier_synnex", depts_synnex, 4)
            synnex_sales = _pick_department(depts_synnex, "Inside sales")
            synnex_contact = next((m for m in mem_synnex if m.department_id == synnex_sales.id), mem_synnex[0])

            sup_ingram = Supplier.objects.create(
                uuid=demo_u("supplier.ingram_micro_benelux"),
                name="Ingram Micro Benelux",
                contact_person="Channel Desk",
                email="orders@ingram.demo.local",
            )
            sup_synnex = Supplier.objects.create(
                uuid=demo_u("supplier.td_synnex_netherlands"),
                name="TD SYNNEX Netherlands",
                contact_person="Inside Sales",
                email="nl.inside@tdsynnex.demo.local",
            )

            # --- CRM: clients + lead (three companies) --------------------------------------------
            org_vandijk = _create_organization(
                "client_vandijk",
                "Van Dijk Facilities B.V.",
                [OrganizationRole.ROLE_CLIENT],
                billing_city="Amsterdam",
                website="https://vandijk-facilities.demo.local",
            )
            org_houthaven = _create_organization(
                "client_houthaven",
                "Houthaven Logistics",
                [OrganizationRole.ROLE_CLIENT],
                billing_city="Utrecht",
                website="https://houthaven-logistics.demo.local",
            )
            org_degeul = _create_organization(
                "lead_degeul",
                "Stadscafé De Geul",
                [OrganizationRole.ROLE_LEAD],
                billing_city="Maastricht",
                website="https://degeul.demo.local",
                lead_pipeline_status=Organization.PIPELINE_PROPOSAL,
            )

            for org, key in (
                (org_vandijk, "client_vandijk"),
                (org_houthaven, "client_houthaven"),
                (org_degeul, "lead_degeul"),
            ):
                n_depts = random.randint(2, 5)
                dept_names = random.sample(DEPARTMENT_NAMES, k=min(n_depts, len(DEPARTMENT_NAMES)))
                depts = _add_departments(org, key, dept_names)
                _add_people_and_memberships(org, key, depts, random.randint(5, 11))

            # --- CRM: hobbies, personal events, life-event notes -----------------------------------
            persons_list = list(Person.objects.order_by("pk"))
            for idx, person in enumerate(persons_list):
                PersonHobby.objects.create(
                    uuid=demo_u(f"personhobby.{idx}.0"),
                    person=person,
                    name=HOBBY_NAMES[idx % len(HOBBY_NAMES)],
                    sort_order=0,
                )
                if idx % 2 == 0:
                    PersonHobby.objects.create(
                        uuid=demo_u(f"personhobby.{idx}.1"),
                        person=person,
                        name=HOBBY_NAMES[(idx + 5) % len(HOBBY_NAMES)],
                        sort_order=1,
                    )
                PersonEvent.objects.create(
                    uuid=demo_u(f"personevent.{idx}"),
                    person=person,
                    name="Follow-up coffee" if idx % 3 else "Birthday",
                    event_date=date(2026, 4, 8) + timedelta(days=idx * 6),
                    reminder=PersonEvent.REMINDER_1_WEEK
                    if idx % 2
                    else PersonEvent.REMINDER_ON_DAY,
                )
                if idx % 3 == 0:
                    PersonLifeEvent.objects.create(
                        uuid=demo_u(f"personlifeevent.{idx}"),
                        person=person,
                        occurred_on=date(2026, 1, 12) + timedelta(days=idx),
                        note=LIFE_EVENT_NOTES[idx % len(LIFE_EVENT_NOTES)],
                    )

            # --- CRM: organisation invoices (clients) ---------------------------------------------
            OrganizationInvoice.objects.create(
                uuid=demo_u("orginvoice.vandijk.1"),
                organization=org_vandijk,
                invoice_number="VD-INV-2025-1042",
                issued_on=date(2025, 11, 18),
                amount=Decimal("18420.50"),
            )
            OrganizationInvoice.objects.create(
                uuid=demo_u("orginvoice.vandijk.2"),
                organization=org_vandijk,
                invoice_number="VD-INV-2026-0017",
                issued_on=date(2026, 2, 3),
                amount=Decimal("3200.00"),
            )
            OrganizationInvoice.objects.create(
                uuid=demo_u("orginvoice.houthaven.1"),
                organization=org_houthaven,
                invoice_number="HL-2025-9901",
                issued_on=date(2025, 12, 2),
                amount=Decimal("9875.25"),
            )
            OrganizationInvoice.objects.create(
                uuid=demo_u("orginvoice.houthaven.2"),
                organization=org_houthaven,
                invoice_number="HL-2026-0104",
                issued_on=date(2026, 2, 20),
                amount=Decimal("4520.00"),
            )

            # --- CRM: network partners + links ------------------------------------------------------
            org_printcare = _create_organization(
                "network_printcare",
                "PrintCare Cooperative",
                [OrganizationRole.ROLE_NETWORK],
                billing_city="Eindhoven",
                website="https://printcare.demo.local",
                network_value_proposition="Nationwide first-line printer repair and SLA-backed toner logistics.",
                network_industry_niche="Office print services",
            )
            org_cortex = _create_organization(
                "network_cortex",
                "Cortex IT Alliance",
                [OrganizationRole.ROLE_NETWORK],
                billing_city="Den Haag",
                website="https://cortex-alliance.demo.local",
                network_value_proposition="Microsoft 365, identity, and endpoint management for SMB fleets.",
                network_industry_niche="Managed IT & security",
            )
            depts_pc = _add_departments(org_printcare, "network_printcare", ["Partner success", "Field ops"])
            depts_cx = _add_departments(org_cortex, "network_cortex", ["Alliance desk", "Technical board"])
            _add_people_and_memberships(org_printcare, "network_printcare", depts_pc, 3)
            _add_people_and_memberships(org_cortex, "network_cortex", depts_cx, 3)

            # Network partner ↔ supplier / client / lead (unique pairs)
            links = [
                ("networklink.printcare.vandijk", org_printcare, org_vandijk, "On-site break-fix for Amsterdam sites."),
                ("networklink.printcare.houthaven", org_printcare, org_houthaven, "Preferred logistics for spare parts."),
                ("networklink.printcare.ingram", org_printcare, org_ingram, "Channel training and demo stock."),
                ("networklink.cortex.degeul", org_cortex, org_degeul, "POS Wi-Fi and guest network review."),
                ("networklink.cortex.synnex", org_cortex, org_synnex, "SMB security bundle referrals."),
                ("networklink.cortex.houthaven", org_cortex, org_houthaven, "WMS integration partner."),
            ]
            for key, net, linked, notes in links:
                OrganizationNetworkLink.objects.create(
                    uuid=demo_u(key),
                    network_organization=net,
                    linked_organization=linked,
                    notes=notes,
                )

            # --- Products (explicit article_number UUIDs + supplier CRM) ---------------------------
            c_print = categories["Printers & MFPs"]
            c_scan = categories["Scanners"]
            c_sup = categories["Supplies"]
            c_svc = categories["Services"]

            def create_product(
                article_key: str,
                brand: str,
                model_type: str,
                supplier: Supplier,
                category: Category,
                cost: float | None,
                *,
                crm_org: Organization,
                crm_dept: Department,
                crm_contact: OrganizationPerson,
                order_no: str = "",
                desc: str = "",
                usps: str = "",
                fixed: Decimal | None = None,
                margin: bool = True,
            ) -> Product:
                return Product.objects.create(
                    article_number=demo_u(f"article.{article_key}"),
                    brand=brand,
                    model_type=model_type,
                    supplier=supplier,
                    category=category,
                    cost_price=None if fixed is not None else Decimal(str(cost)),
                    fixed_sales_price=fixed,
                    profit_profile=profile,
                    supplier_order_number=order_no or f"DEMO-{article_key}",
                    description=desc,
                    usps=usps,
                    show_in_price_list=True,
                    is_margin_product=margin,
                    price_last_changed=None,
                    supplier_crm_organization=crm_org,
                    supplier_crm_department=crm_dept,
                    supplier_crm_contact=crm_contact,
                )

            products: dict[str, Product] = {}

            products["epson_wfc5390"] = create_product(
                "epson_wfc5390",
                "Epson",
                "WorkForce Pro WF-C5390DW",
                sup_ingram,
                c_print,
                289.00,
                crm_org=org_ingram,
                crm_dept=ingram_sales,
                crm_contact=ingram_contact,
                order_no="EPS-WFC5390",
                desc="Colour inkjet for workgroups; low cost per page.",
                usps="Fast first page out\nDuplex standard\nWi-Fi & Ethernet",
            )
            products["hp_m404"] = create_product(
                "hp_m404",
                "HP",
                "LaserJet Pro M404dn",
                sup_synnex,
                c_print,
                198.50,
                crm_org=org_synnex,
                crm_dept=synnex_sales,
                crm_contact=synnex_contact,
                order_no="HP-M404DN",
                desc="Mono laser for small teams; secure printing.",
                usps="Auto duplex\nUSB & Ethernet",
            )
            products["canon_c3830i"] = create_product(
                "canon_c3830i",
                "Canon",
                "imageRUNNER ADVANCE DX C3830i",
                sup_ingram,
                c_print,
                2450.00,
                crm_org=org_ingram,
                crm_dept=ingram_sales,
                crm_contact=ingram_contact,
                order_no="CAN-C3830I",
                desc="A3 colour MFP for busy departments.",
                usps="Scan to cloud\nHigh toner yield",
            )
            products["brother_ads4700"] = create_product(
                "brother_ads4700",
                "Brother",
                "ADS-4700W",
                sup_synnex,
                c_scan,
                419.00,
                crm_org=org_synnex,
                crm_dept=synnex_sales,
                crm_contact=synnex_contact,
                order_no="BR-ADS4700W",
                desc="Desktop document scanner with wireless.",
                usps="50 ppm\nDual CIS",
            )
            products["fujitsu_fi8170"] = create_product(
                "fujitsu_fi8170",
                "Fujitsu",
                "fi-8170",
                sup_ingram,
                c_scan,
                1125.00,
                crm_org=org_ingram,
                crm_dept=ingram_sales,
                crm_contact=ingram_contact,
                order_no="FJ-FI8170",
                desc="Production-grade departmental scanner.",
                usps="80 ppm / 160 ipm\nUltrasonic double-feed detection",
            )
            products["zebra_zd421"] = create_product(
                "zebra_zd421",
                "Zebra",
                "ZD421t",
                sup_synnex,
                c_print,
                312.00,
                crm_org=org_synnex,
                crm_dept=synnex_sales,
                crm_contact=synnex_contact,
                order_no="ZB-ZD421T",
                desc="Thermal transfer label printer; USB & Bluetooth.",
                usps="Easy media loading\nLink-OS",
            )
            products["dell_promff"] = create_product(
                "dell_promff",
                "Dell",
                "Pro Max PC (Micro form factor)",
                sup_synnex,
                c_print,
                899.00,
                crm_org=org_synnex,
                crm_dept=synnex_sales,
                crm_contact=synnex_contact,
                order_no="DL-PROMFF",
                desc="Compact desktop for kiosk or reception PC.",
                usps="VESA mountable\nLow noise",
            )
            products["3m_pf24"] = create_product(
                "3m_pf24",
                "3M",
                'Privacy filter 24" widescreen',
                sup_ingram,
                c_sup,
                48.90,
                crm_org=org_ingram,
                crm_dept=ingram_sales,
                crm_contact=ingram_contact,
                order_no="3M-PF24W",
                desc="Anti-glare privacy screen.",
                usps="Tool-less attachment",
            )
            products["paper_a4"] = create_product(
                "paper_a4",
                "Clairefontaine",
                "A4 paper 80 g/m² (5×500 sheets)",
                sup_synnex,
                c_sup,
                24.50,
                crm_org=org_synnex,
                crm_dept=synnex_sales,
                crm_contact=synnex_contact,
                order_no="CF-A4-5R",
                desc="Office copy paper pallet-friendly case.",
                usps="FSC mix credit",
            )
            products["apc_br1500"] = create_product(
                "apc_br1500",
                "APC",
                "Back-UPS Pro BR1500G",
                sup_ingram,
                c_sup,
                189.00,
                crm_org=org_ingram,
                crm_dept=ingram_sales,
                crm_contact=ingram_contact,
                order_no="APC-BR1500G",
                desc="Line-interactive UPS for small server or MFP.",
                usps="LCD display\nReplaceable battery",
            )
            products["hp_tray_m404"] = create_product(
                "hp_tray_m404",
                "HP",
                "550-sheet input tray (M404 series)",
                sup_synnex,
                c_sup,
                119.00,
                crm_org=org_synnex,
                crm_dept=synnex_sales,
                crm_contact=synnex_contact,
                order_no="HP-M404-TRAY",
                desc="Optional second tray for LaserJet Pro M404.",
                usps="Easy install",
            )
            products["svc_install"] = create_product(
                "svc_install",
                "NovaQuote Demo",
                "On-site install & configuration (half day)",
                sup_ingram,
                c_svc,
                None,
                crm_org=org_ingram,
                crm_dept=ingram_sales,
                crm_contact=ingram_contact,
                order_no="SVC-INSTALL-4H",
                desc="Professional setup of printer/MFP on customer network.",
                usps="Test print included\nUser training (30 min)",
                fixed=Decimal("275.00"),
                margin=False,
            )

            tray_opt = products["hp_tray_m404"]
            main_hp = products["hp_m404"]

            # Catalog supplier offers (one preferred row mirrors Product.supplier / cost).
            for _key, p in products.items():
                if p.supplier_id and not p.product_suppliers.exists():
                    ProductSupplier.objects.create(
                        product=p,
                        supplier_id=p.supplier_id,
                        cost_price=p.cost_price,
                        supplier_order_number=p.supplier_order_number or "",
                        is_preferred=True,
                        sort_order=0,
                    )

            # Demo: alternate supplier on one printer (multi-supplier proposal / price list preferred).
            ProductSupplier.objects.get_or_create(
                product=products["epson_wfc5390"],
                supplier=sup_synnex,
                defaults={
                    "cost_price": Decimal("310.00"),
                    "supplier_order_number": "SYN-WFC5390",
                    "lead_time_days": 10,
                    "payment_terms": "Net 45",
                    "payment_terms_days": 45,
                    "is_preferred": False,
                    "sort_order": 1,
                },
            )

            products["canon_c3830i"].profit_profile = profile_ent
            products["canon_c3830i"].save(update_fields=["profit_profile"])

            _bump_product_cost(products["epson_wfc5390"], Decimal("275.00"))
            _bump_product_cost(products["epson_wfc5390"], Decimal("265.50"))
            _bump_product_cost(products["hp_m404"], Decimal("189.00"))

            ProductOption.objects.create(
                uuid=demo_u("productoption.hp_m404_extra_tray"),
                main_product=main_hp,
                option_product=tray_opt,
                short_description="Extra 550-sheet tray",
                sort_order=0,
            )
            ProductOption.objects.create(
                uuid=demo_u("productoption.hp_m404_ups"),
                main_product=main_hp,
                option_product=products["apc_br1500"],
                short_description="UPS (clean power)",
                sort_order=10,
            )
            ProductOption.objects.create(
                uuid=demo_u("productoption.hp_m404_privacy"),
                main_product=main_hp,
                option_product=products["3m_pf24"],
                short_description='24" privacy filter (desk display)',
                sort_order=20,
            )

            epson = products["epson_wfc5390"]
            ProductOption.objects.create(
                uuid=demo_u("productoption.epson_ups"),
                main_product=epson,
                option_product=products["apc_br1500"],
                short_description="UPS for inkjet / small workgroup",
                sort_order=0,
            )
            ProductOption.objects.create(
                uuid=demo_u("productoption.epson_paper"),
                main_product=epson,
                option_product=products["paper_a4"],
                short_description="Starter A4 paper case",
                sort_order=10,
            )
            ProductOption.objects.create(
                uuid=demo_u("productoption.epson_install"),
                main_product=epson,
                option_product=products["svc_install"],
                short_description="On-site install (half day)",
                sort_order=20,
            )

            canon = products["canon_c3830i"]
            ProductOption.objects.create(
                uuid=demo_u("productoption.canon_privacy"),
                main_product=canon,
                option_product=products["3m_pf24"],
                short_description="Privacy filter bundle",
                sort_order=0,
            )
            ProductOption.objects.create(
                uuid=demo_u("productoption.canon_ups"),
                main_product=canon,
                option_product=products["apc_br1500"],
                short_description="UPS for MFP + PC",
                sort_order=10,
            )
            ProductOption.objects.create(
                uuid=demo_u("productoption.canon_paper"),
                main_product=canon,
                option_product=products["paper_a4"],
                short_description="High-volume paper case",
                sort_order=20,
            )

            brother = products["brother_ads4700"]
            ProductOption.objects.create(
                uuid=demo_u("productoption.brother_paper"),
                main_product=brother,
                option_product=products["paper_a4"],
                short_description="Archival / office paper case",
                sort_order=0,
            )
            ProductOption.objects.create(
                uuid=demo_u("productoption.brother_install"),
                main_product=brother,
                option_product=products["svc_install"],
                short_description="Scanner desk setup & driver policy",
                sort_order=10,
            )

            fujitsu = products["fujitsu_fi8170"]
            ProductOption.objects.create(
                uuid=demo_u("productoption.fujitsu_paper"),
                main_product=fujitsu,
                option_product=products["paper_a4"],
                short_description="Feeder test / calibration stock",
                sort_order=0,
            )
            ProductOption.objects.create(
                uuid=demo_u("productoption.fujitsu_install"),
                main_product=fujitsu,
                option_product=products["svc_install"],
                short_description="Production scanner rollout block",
                sort_order=10,
            )

            ProductOption.objects.create(
                uuid=demo_u("productoption.zebra_ups"),
                main_product=products["zebra_zd421"],
                option_product=products["apc_br1500"],
                short_description="UPS for label station",
                sort_order=0,
            )
            ProductOption.objects.create(
                uuid=demo_u("productoption.zebra_install"),
                main_product=products["zebra_zd421"],
                option_product=products["svc_install"],
                short_description="Media calibration visit",
                sort_order=10,
            )

            dell = products["dell_promff"]
            ProductOption.objects.create(
                uuid=demo_u("productoption.dell_privacy"),
                main_product=dell,
                option_product=products["3m_pf24"],
                short_description="Privacy filter (kiosk display)",
                sort_order=0,
            )
            ProductOption.objects.create(
                uuid=demo_u("productoption.dell_ups"),
                main_product=dell,
                option_product=products["apc_br1500"],
                short_description="UPS for micro PC + screen",
                sort_order=10,
            )

            comb = Combination.objects.create(
                uuid=demo_u("combination.small_office_bundle"),
                name="Small office: print & scan bundle",
                description="HP laser, Brother scanner, paper case and installation service.",
                usps="Ships from one order\n5% bundle discount on hardware",
                offer_type=Combination.OFFER_TYPE_DISCOUNT_PERCENTAGE,
                discount_percentage=Decimal("5.00"),
                combination_sales_price=Decimal("0.01"),
            )
            ci1 = CombinationItem.objects.create(
                uuid=demo_u("combinationitem.bundle.hp_m404"),
                combination=comb,
                product=main_hp,
                sort_order=0,
            )
            ci1.selected_options.set([tray_opt])
            CombinationItem.objects.create(
                uuid=demo_u("combinationitem.bundle.brother_scanner"),
                combination=comb,
                product=products["brother_ads4700"],
                sort_order=10,
            )
            CombinationItem.objects.create(
                uuid=demo_u("combinationitem.bundle.paper"),
                combination=comb,
                product=products["paper_a4"],
                sort_order=20,
            )
            CombinationItem.objects.create(
                uuid=demo_u("combinationitem.bundle.install_svc"),
                combination=comb,
                product=products["svc_install"],
                sort_order=30,
            )
            comb.combination_sales_price = comb.offer_price
            comb.save(update_fields=["combination_sales_price"])

            _attach_demo_images(products, comb, self.stdout)

            cd36 = ContractDuration.objects.create(
                uuid=demo_u("contractduration.maintenance_36m"),
                name="3 years maintenance",
                duration_months=36,
                hardware_fee_percentage=Decimal("8.00"),
                visits_per_contract=Decimal("6.00"),
                is_active=True,
            )
            cd60 = ContractDuration.objects.create(
                uuid=demo_u("contractduration.maintenance_60m"),
                name="5 years maintenance",
                duration_months=60,
                hardware_fee_percentage=Decimal("6.50"),
                visits_per_contract=Decimal("10.00"),
                is_active=True,
            )

            vd_contact = (
                OrganizationPerson.objects.filter(
                    organization=org_vandijk, is_primary_contact=True
                ).first()
                or OrganizationPerson.objects.filter(organization=org_vandijk).first()
            )
            prop1 = Proposal.objects.create(
                uuid=demo_u("proposal.vandijk_refresh"),
                reference="2026-0142 – Van Dijk print refresh",
                created_by=admin_user,
                client_crm_organization=org_vandijk,
                client_crm_department=vd_contact.department if vd_contact else None,
                client_crm_contact=vd_contact,
                time_per_product_snapshot=Decimal("15.00"),
                minimum_visit_snapshot=Decimal("60.00"),
                hourly_rate_snapshot=Decimal("75.00"),
            )
            canon_ps = ProductSupplier.objects.get(product=canon, is_preferred=True)
            canon_unit = canon.calculated_sales_price or Decimal("0")
            ProposalLine.objects.create(
                uuid=demo_u("proposalline.vandijk.canon"),
                proposal=prop1,
                sort_order=0,
                line_type=ProposalLine.LINE_TYPE_PRODUCT,
                product=canon,
                quantity=Decimal("1"),
                unit_price_snapshot=canon_unit,
                line_total_snapshot=canon_unit,
                name_snapshot=str(canon),
                product_supplier=canon_ps,
                supplier_name_snapshot=canon_ps.supplier.name,
            )
            bundle_unit = comb.offer_price
            ProposalLine.objects.create(
                uuid=demo_u("proposalline.vandijk.bundle"),
                proposal=prop1,
                sort_order=10,
                line_type=ProposalLine.LINE_TYPE_COMBINATION,
                combination=comb,
                quantity=Decimal("2"),
                unit_price_snapshot=bundle_unit,
                line_total_snapshot=bundle_unit * Decimal("2"),
                name_snapshot=comb.name,
            )
            for sort_i, cd in enumerate((cd36, cd60)):
                ProposalContractSnapshot.objects.create(
                    uuid=demo_u(f"proposalcontractsnap.vandijk.{sort_i}"),
                    proposal=prop1,
                    contract_duration=cd,
                    contract_duration_uuid=cd.uuid,
                    sort_order=sort_i,
                    name=cd.name,
                    duration_months=cd.duration_months,
                    hardware_fee_percentage=cd.hardware_fee_percentage,
                    visits_per_contract=cd.visits_per_contract,
                )
            ProposalHistory.objects.create(
                uuid=demo_u("proposalhistory.vandijk.created"),
                proposal=prop1,
                action=ProposalHistory.ACTION_CREATED,
                description="Proposal created from discovery workshop.",
                user=admin_user,
            )
            ProposalHistory.objects.create(
                uuid=demo_u("proposalhistory.vandijk.saved"),
                proposal=prop1,
                action=ProposalHistory.ACTION_SAVED,
                description="Saved pricing after supplier re-quote.",
                user=admin_user,
            )

            hh_contact = (
                OrganizationPerson.objects.filter(
                    organization=org_houthaven, is_primary_contact=True
                ).first()
                or OrganizationPerson.objects.filter(organization=org_houthaven).first()
            )
            prop2 = Proposal.objects.create(
                uuid=demo_u("proposal.houthaven_scan"),
                reference="Houthaven – scanner pilot",
                created_by=admin_user,
                client_crm_organization=org_houthaven,
                client_crm_department=hh_contact.department if hh_contact else None,
                client_crm_contact=hh_contact,
                time_per_product_snapshot=Decimal("15.00"),
                minimum_visit_snapshot=Decimal("60.00"),
                hourly_rate_snapshot=Decimal("75.00"),
            )
            scan = products["brother_ads4700"]
            scan_ps = ProductSupplier.objects.get(product=scan, is_preferred=True)
            su = scan.calculated_sales_price or Decimal("0")
            ProposalLine.objects.create(
                uuid=demo_u("proposalline.houthaven.scan"),
                proposal=prop2,
                sort_order=0,
                line_type=ProposalLine.LINE_TYPE_PRODUCT,
                product=scan,
                quantity=Decimal("6"),
                unit_price_snapshot=su,
                line_total_snapshot=su * Decimal("6"),
                name_snapshot=str(scan),
                product_supplier=scan_ps,
                supplier_name_snapshot=scan_ps.supplier.name,
            )
            ProposalContractSnapshot.objects.create(
                uuid=demo_u("proposalcontractsnap.houthaven.0"),
                proposal=prop2,
                contract_duration=cd36,
                contract_duration_uuid=cd36.uuid,
                sort_order=0,
                name=cd36.name,
                duration_months=cd36.duration_months,
                hardware_fee_percentage=cd36.hardware_fee_percentage,
                visits_per_contract=cd36.visits_per_contract,
            )
            ProposalHistory.objects.create(
                uuid=demo_u("proposalhistory.houthaven.created"),
                proposal=prop2,
                action=ProposalHistory.ACTION_CREATED,
                description="Pilot line for warehouse documentation desks.",
                user=admin_user,
            )

            # --- Invoices then orders (mirrors UI: invoice → mark sent → order) --------------
            inv_vd = create_invoice_for_proposal(prop1, admin_user, currency_code="EUR")
            mark_invoice_sent(inv_vd)
            order_vd = create_order_from_proposal(prop1, admin_user, invoice=inv_vd)
            Order.objects.filter(pk=order_vd.pk).update(uuid=demo_u("order.vandijk_refresh"))
            order_vd.refresh_from_db()
            order_vd.status = Order.STATUS_SENT
            order_vd.note = (
                "Released to suppliers — bundle may ship in two waves; confirm dock hours with Van Dijk."
            )
            order_vd.save(update_fields=["status", "note"])

            vd_items = list(
                OrderLineItem.objects.filter(order_line__order=order_vd).order_by("id")
            )
            for i, oli in enumerate(vd_items):
                oli.ordered_at = django_timezone.now() - timedelta(days=max(1, 3 - i))
                oli.expected_delivery = date.today() + timedelta(days=5 + i * 2)
                oli.save(update_fields=["ordered_at", "expected_delivery"])
            if vd_items:
                vd_items[0].delivered_at = django_timezone.now() - timedelta(days=1)
                vd_items[0].save(update_fields=["delivered_at"])

            inv_hh = create_invoice_for_proposal(prop2, admin_user, currency_code="EUR")
            mark_invoice_sent(inv_hh)
            order_hh = create_order_from_proposal(prop2, admin_user, invoice=inv_hh)
            Order.objects.filter(pk=order_hh.pk).update(uuid=demo_u("order.houthaven_scan"))
            order_hh.refresh_from_db()
            # Draft: created but not yet released to suppliers
            order_hh.status = Order.STATUS_DRAFT
            order_hh.save(update_fields=["status"])

        self.stdout.write(self.style.SUCCESS("Demo data loaded."))
        self.stdout.write(f"  Superuser: {username} / {password} (change this password!)")
        self.stdout.write(
            f"  Frontend demo users (password «{password}»): sales (Sales), catalog (Catalog manager), buyer (Procurement)."
        )
        self.stdout.write(
            '  General settings: site name "NovaQuote", Teal (#008080) color scheme, custom logo cleared (bundled default shown).'
        )
        self.stdout.write("  Stable UUID v5 on seeded rows (organizations, persons, products article_number, …).")
        self.stdout.write(
            "  CRM: suppliers/clients/lead, memberships, roles, hobbies, events, life events, "
            "invoices, network links."
        )
        self.stdout.write(
            "  Catalog: categories, profit profiles, products + many options + placeholder images, "
            "price history, combinations, contract durations, saved proposals, orders (with line items)."
        )
