"""Forms for Contacts (CRM) frontend editing."""

from django import forms
from django.forms.models import BaseInlineFormSet, inlineformset_factory
from django.utils.translation import gettext_lazy as _

from .models import (
    Department,
    Organization,
    OrganizationNetworkLink,
    OrganizationPerson,
    OrganizationRole,
    Person,
    PersonEvent,
    PersonHobby,
    PersonLifeEvent,
)


INPUT_CLASS = "w-full text-sm rounded border border-slate-300 px-3 py-2 focus:ring-2 focus:ring-[var(--brand)] focus:border-[var(--brand)]"
TEXTAREA_CLASS = INPUT_CLASS + " min-h-[5rem]"
CHECKBOX_CLASS = "rounded border-slate-300 text-[var(--brand)] focus:ring-[var(--brand)]"


def _style_fields(form: forms.Form, skip: frozenset | None = None) -> None:
    skip = skip or frozenset()
    for name, field in form.fields.items():
        if name in skip:
            continue
        w = field.widget
        if isinstance(w, forms.CheckboxInput):
            w.attrs.setdefault("class", CHECKBOX_CLASS)
        elif isinstance(w, (forms.Textarea,)):
            w.attrs.setdefault("class", TEXTAREA_CLASS)
        elif isinstance(w, forms.CheckboxSelectMultiple):
            w.attrs.setdefault("class", "space-y-2")
        else:
            w.attrs.setdefault("class", INPUT_CLASS)


class OrganizationForm(forms.ModelForm):
    """Organization with role checkboxes (synced to OrganizationRole rows)."""

    field_order = [
        "name",
        "legal_name",
        "vat_number",
        "coc_number",
        "roles",
        "billing_line1",
        "billing_line2",
        "billing_city",
        "billing_postal_code",
        "billing_country",
        "shipping_line1",
        "shipping_line2",
        "shipping_city",
        "shipping_postal_code",
        "shipping_country",
        "email",
        "phone",
        "website",
        "iban",
        "bic_swift",
        "payment_terms",
        "currency",
        "credit_limit",
        "incoterms",
        "lead_time_days",
        "moq",
        "network_value_proposition",
        "network_industry_niche",
        "lead_pipeline_status",
        "suppress_auto_client_promotion",
        "client_promotion_override",
    ]

    roles = forms.MultipleChoiceField(
        label=_("Roles"),
        choices=OrganizationRole.ROLE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("A company can have several roles at once (e.g. supplier and client)."),
    )

    class Meta:
        model = Organization
        fields = [
            "name",
            "legal_name",
            "vat_number",
            "coc_number",
            "billing_line1",
            "billing_line2",
            "billing_city",
            "billing_postal_code",
            "billing_country",
            "shipping_line1",
            "shipping_line2",
            "shipping_city",
            "shipping_postal_code",
            "shipping_country",
            "email",
            "phone",
            "website",
            "iban",
            "bic_swift",
            "payment_terms",
            "currency",
            "credit_limit",
            "incoterms",
            "lead_time_days",
            "moq",
            "network_value_proposition",
            "network_industry_niche",
            "lead_pipeline_status",
            "suppress_auto_client_promotion",
            "client_promotion_override",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self, skip=frozenset({"roles", "suppress_auto_client_promotion"}))
        self.fields["suppress_auto_client_promotion"].widget.attrs.setdefault("class", CHECKBOX_CLASS)
        if self.instance.pk:
            self.fields["roles"].initial = list(
                self.instance.role_assignments.values_list("role", flat=True)
            )

    def clean(self):
        cleaned_data = super().clean()
        roles = list(cleaned_data.get("roles") or [])
        # Mirror _sync_roles: manual client mode always adds CLIENT.
        if (
            cleaned_data.get("client_promotion_override") == Organization.PROMOTION_MANUAL_CLIENT
            and OrganizationRole.ROLE_CLIENT not in roles
        ):
            roles.append(OrganizationRole.ROLE_CLIENT)
        if not roles:
            self.add_error(
                "roles",
                forms.ValidationError(
                    _(
                        "Select at least one role. "
                        "With no roles, the company is not shown under Suppliers, Clients, Leads, or Network."
                    ),
                    code="at_least_one_role",
                ),
            )
        return cleaned_data

    def save(self, commit=True):
        org = super().save(commit=commit)
        if commit:
            self._sync_roles(org)
        return org

    def _sync_roles(self, org: Organization) -> None:
        selected = list(self.cleaned_data.get("roles") or [])
        if (
            self.cleaned_data.get("client_promotion_override") == Organization.PROMOTION_MANUAL_CLIENT
            and OrganizationRole.ROLE_CLIENT not in selected
        ):
            selected.append(OrganizationRole.ROLE_CLIENT)
        OrganizationRole.objects.filter(organization=org).delete()
        for role in selected:
            OrganizationRole.objects.create(organization=org, role=role)


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = [
            "first_name",
            "last_name",
            "personal_email",
            "personal_mobile",
            "linkedin_url",
            "date_of_birth",
            "communication_preferences",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class PersonHobbyEntryForm(forms.ModelForm):
    class Meta:
        model = PersonHobby
        fields = ("name",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = False
        self.fields["name"].widget.attrs.setdefault("class", INPUT_CLASS)
        self.fields["name"].label = _("Hobby or interest")
        if "DELETE" in self.fields:
            self.fields["DELETE"].widget.attrs.setdefault("class", CHECKBOX_CLASS)


class BaseHobbyFormSet(BaseInlineFormSet):
    def save(self, commit=True):
        """Omit blank rows; delete rows marked DELETE; drop empty-named existing rows."""
        order = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            cd = form.cleaned_data
            if cd.get("DELETE"):
                if form.instance.pk:
                    form.instance.delete()
                continue
            name = (cd.get("name") or "").strip()
            if not name:
                if form.instance.pk:
                    form.instance.delete()
                continue
            obj = form.save(commit=False)
            obj.sort_order = order
            order += 1
            if commit:
                obj.save()
        return []


class PersonEventEntryForm(forms.ModelForm):
    class Meta:
        model = PersonEvent
        fields = ("name", "event_date", "reminder")
        widgets = {
            "event_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = False
        self.fields["event_date"].required = False
        self.fields["name"].widget.attrs.setdefault("class", INPUT_CLASS)
        self.fields["reminder"].widget.attrs.setdefault("class", INPUT_CLASS)
        if "DELETE" in self.fields:
            self.fields["DELETE"].widget.attrs.setdefault("class", CHECKBOX_CLASS)

    def clean(self):
        cd = super().clean()
        if cd.get("DELETE"):
            return cd
        name = (cd.get("name") or "").strip()
        ed = cd.get("event_date")
        if name and not ed:
            self.add_error("event_date", forms.ValidationError(_("Required when the event has a name.")))
        if ed and not name:
            self.add_error("name", forms.ValidationError(_("Required when a date is set.")))
        return cd


class BaseEventFormSet(BaseInlineFormSet):
    def save(self, commit=True):
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            cd = form.cleaned_data
            if cd.get("DELETE"):
                if form.instance.pk:
                    form.instance.delete()
                continue
            name = (cd.get("name") or "").strip()
            ed = cd.get("event_date")
            if not name and not ed:
                continue
            obj = form.save(commit=False)
            if commit:
                obj.save()
        return []


PersonHobbyFormSet = inlineformset_factory(
    Person,
    PersonHobby,
    form=PersonHobbyEntryForm,
    formset=BaseHobbyFormSet,
    extra=0,
    can_delete=True,
    min_num=0,
    validate_min=False,
)

PersonEventFormSet = inlineformset_factory(
    Person,
    PersonEvent,
    form=PersonEventEntryForm,
    formset=BaseEventFormSet,
    extra=0,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


class OrganizationNetworkLinkForm(forms.ModelForm):
    """Create a link either from a network partner to an account, or from an account to a partner."""

    class Meta:
        model = OrganizationNetworkLink
        fields = ("network_organization", "linked_organization", "notes")

    def __init__(self, *args, mode: str, anchor_organization: Organization, **kwargs):
        self.mode = mode
        self.anchor_organization = anchor_organization
        super().__init__(*args, **kwargs)
        _style_fields(self, skip=frozenset())

        counterparty_roles = (
            OrganizationRole.ROLE_SUPPLIER,
            OrganizationRole.ROLE_CLIENT,
            OrganizationRole.ROLE_LEAD,
        )

        if mode == "network_anchor":
            self.fields["network_organization"].initial = anchor_organization.pk
            self.fields["network_organization"].widget = forms.HiddenInput()
            linked_ids = OrganizationNetworkLink.objects.filter(
                network_organization=anchor_organization
            ).values_list("linked_organization_id", flat=True)
            self.fields["linked_organization"].queryset = (
                Organization.objects.filter(role_assignments__role__in=counterparty_roles)
                .exclude(pk=anchor_organization.pk)
                .exclude(pk__in=linked_ids)
                .distinct()
                .order_by("name")
            )
            self.fields["linked_organization"].label = _("Company to link")
            self.fields["linked_organization"].help_text = _(
                "Supplier, client, or lead organization you know this partner through."
            )
        else:
            self.fields["linked_organization"].initial = anchor_organization.pk
            self.fields["linked_organization"].widget = forms.HiddenInput()
            net_ids = OrganizationNetworkLink.objects.filter(
                linked_organization=anchor_organization
            ).values_list("network_organization_id", flat=True)
            self.fields["network_organization"].queryset = (
                Organization.objects.filter(role_assignments__role=OrganizationRole.ROLE_NETWORK)
                .exclude(pk=anchor_organization.pk)
                .exclude(pk__in=net_ids)
                .distinct()
                .order_by("name")
            )
            self.fields["network_organization"].label = _("Network partner")
            self.fields["network_organization"].help_text = _("Select the network partner to associate with this company.")

    def clean(self):
        cleaned_data = super().clean()
        if self.mode == "network_anchor":
            cleaned_data["network_organization"] = self.anchor_organization
        else:
            cleaned_data["linked_organization"] = self.anchor_organization
        net = cleaned_data.get("network_organization")
        linked = cleaned_data.get("linked_organization")
        if net and linked and net.pk == linked.pk:
            raise forms.ValidationError(
                _("Network partner and linked company must be different organizations.")
            )
        return cleaned_data


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ("name", "email", "phone", "notes")

    def __init__(self, *args, organization: Organization | None = None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.organization:
            obj.organization = self.organization
        if commit:
            obj.save()
        return obj


class OrganizationPersonForm(forms.ModelForm):
    class Meta:
        model = OrganizationPerson
        fields = ("person", "department", "job_title", "company_email", "company_phone", "phone_extension", "is_primary_contact")

    def __init__(self, *args, organization: Organization | None = None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)
        _style_fields(self, skip=frozenset({"is_primary_contact"}))
        self.fields["is_primary_contact"].widget.attrs.setdefault("class", CHECKBOX_CLASS)
        if organization:
            self.fields["department"].queryset = Department.objects.filter(organization=organization).order_by(
                "name"
            )
        self.fields["person"].queryset = Person.objects.order_by("last_name", "first_name")
        self.fields["person"].label_from_instance = lambda p: f"{p.first_name} {p.last_name}".strip() or str(p.pk)

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.organization:
            obj.organization = self.organization
        if commit:
            obj.save()
        return obj


class PersonOrganizationMembershipForm(forms.ModelForm):
    """Link an existing person to a company + optional department (from the person detail flow)."""

    class Meta:
        model = OrganizationPerson
        fields = (
            "organization",
            "department",
            "job_title",
            "company_email",
            "company_phone",
            "phone_extension",
            "is_primary_contact",
        )

    def __init__(self, *args, person: Person | None = None, **kwargs):
        self.person = person
        super().__init__(*args, **kwargs)
        _style_fields(self, skip=frozenset({"is_primary_contact"}))
        self.fields["is_primary_contact"].widget.attrs.setdefault("class", CHECKBOX_CLASS)
        self.fields["organization"].queryset = Organization.objects.order_by("name")
        self.fields["organization"].label = _("Company")
        # Validation accepts any department PK; clean() ties it to the selected company.
        self.fields["department"].queryset = Department.objects.select_related("organization").order_by(
            "organization__name", "name"
        )
        self.fields["department"].required = False

    def clean(self):
        cleaned = super().clean()
        org = cleaned.get("organization")
        dept = cleaned.get("department")
        if dept and org and dept.organization_id != org.pk:
            self.add_error("department", _("Department must belong to the selected company."))
        if org and self.person:
            qs = OrganizationPerson.objects.filter(organization=org, person=self.person)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("organization", _("This person is already linked to this company."))
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.person:
            obj.person = self.person
        if commit:
            obj.save()
        return obj


class PersonLifeEventForm(forms.ModelForm):
    class Meta:
        model = PersonLifeEvent
        fields = ("occurred_on", "note")

    def __init__(self, *args, person: Person | None = None, **kwargs):
        self.person = person
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.person:
            obj.person = self.person
        if commit:
            obj.save()
        return obj
