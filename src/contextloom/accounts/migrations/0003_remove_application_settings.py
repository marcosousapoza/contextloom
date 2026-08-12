from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_user_password_change_required")]
    operations = [migrations.DeleteModel(name="ApplicationSettings")]
