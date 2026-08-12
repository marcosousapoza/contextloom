from django import forms

from contextloom.knowledge.models import Category, Memory


class OwnerCategoryMixin:
    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        if "parent" in self.fields:
            self.fields["parent"].queryset = Category.objects.filter(owner=owner)
        if "category" in self.fields:
            self.fields["category"].queryset = Category.objects.filter(owner=owner)


class CategoryForm(OwnerCategoryMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name", "description", "parent")


class MemoryForm(OwnerCategoryMixin, forms.ModelForm):
    class Meta:
        model = Memory
        fields = ("category", "content", "priority")
        widgets = {"content": forms.Textarea(attrs={"rows": 8})}


class ImportUploadForm(forms.Form):
    archive = forms.FileField(help_text="ContextLoom ZIP export, up to 10 MB.")
    mode = forms.ChoiceField(choices=[("merge", "Merge"), ("replace", "Replace")])


class ImportConfirmForm(forms.Form):
    confirm = forms.BooleanField(label="Apply this import")
    replace_confirm = forms.CharField(required=False, label='Type "replace" to confirm')

    def __init__(self, *args, mode, **kwargs):
        self.mode = mode
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if self.mode == "replace" and data.get("replace_confirm") != "replace":
            self.add_error("replace_confirm", 'Type "replace" exactly.')
        return data
