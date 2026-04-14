from django.urls import path
from detection.views import RuleDefinitionCreateView

urlpatterns = [
    path("", RuleDefinitionCreateView.as_view(), name="rule-definition-create"),
]
