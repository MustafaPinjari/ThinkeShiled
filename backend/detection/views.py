from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.permissions import IsAdminRole
from detection.engine import FraudDetectionEngine
from detection.serializers import RuleDefinitionSerializer


class RuleDefinitionCreateView(APIView):
    """
    POST /api/v1/rules/

    Add a new RuleDefinition at runtime (ADMIN only).
    The engine hot-reloads rules on the next evaluate_rules() call.
    """

    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = RuleDefinitionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        rule = serializer.save()

        # Notify the engine (engine.add_rule writes the AuditLog entry)
        engine = FraudDetectionEngine()
        engine.add_rule(rule)

        return Response(RuleDefinitionSerializer(rule).data, status=status.HTTP_201_CREATED)
