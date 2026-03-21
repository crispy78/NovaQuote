# Update project state so Combinatie -> Combination and CombinatieItem -> CombinationItem.
# DB tables stay catalogus_combinatie and catalogus_combinatieitem (models use db_table).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0035_rename_all_dutch_fields_to_english"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameModel(old_name="Combinatie", new_name="Combination"),
                migrations.RenameModel(old_name="CombinatieItem", new_name="CombinationItem"),
            ],
            database_operations=[],
        ),
    ]
