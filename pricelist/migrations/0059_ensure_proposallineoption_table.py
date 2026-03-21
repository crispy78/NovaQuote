from django.db import migrations


def ensure_proposallineoption_table(apps, schema_editor):
    """
    Create catalogus_proposallineoption if it's missing.
    This fixes OperationalError: no such table: catalogus_proposallineoption
    on databases that got out of sync with migration 0051.
    """
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(catalogus_proposallineoption)")
        columns = cursor.fetchall()
    if columns:
        # Table already exists, nothing to do.
        return

    # Minimal compatible schema: id, proposal_line_id, option_product_id + unique constraint
    schema_editor.execute(
        """
        CREATE TABLE catalogus_proposallineoption (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_line_id BIGINT NOT NULL,
            option_product_id BIGINT NOT NULL
        )
        """
    )
    schema_editor.execute(
        """
        CREATE UNIQUE INDEX catalogus_proposallineoption_proposal_line_id_option_product_id_uniq
        ON catalogus_proposallineoption (proposal_line_id, option_product_id)
        """
    )


def noop_reverse(apps, schema_editor):
    # Don't drop the table on reverse; it may contain data.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0058_general_settings_site_name"),
    ]

    operations = [
        migrations.RunPython(ensure_proposallineoption_table, noop_reverse),
    ]

