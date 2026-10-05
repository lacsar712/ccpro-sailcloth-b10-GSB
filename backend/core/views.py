from django.db import IntegrityError, transaction
from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ClothRoll, DipRun, Loft
from .permissions import IsAdminRole
from .serializers import (
    ClothRollSerializer,
    DipRunSerializer,
    LoftRenameSerializer,
    LoftSerializer,
)


class LoftViewSet(viewsets.ModelViewSet):
    queryset = Loft.objects.annotate(roll_count=Count("rolls")).all()
    serializer_class = LoftSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAdminRole()]

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAdminRole],
        url_path="rename",
    )
    def rename(self, request, pk=None):
        """管理员改间名专用动作：只改 Loft.name，不触碰任何布卷。"""
        loft = self.get_object()
        serializer = LoftRenameSerializer(
            data=request.data, instance=loft, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                loft.name = serializer.validated_data["name"]
                loft.save(update_fields=["name"])
        except IntegrityError:
            return Response(
                {"name": ["已存在同名帆布间，两间不得撞名"]},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self.get_serializer(loft).data)


class ClothRollViewSet(viewsets.ModelViewSet):
    serializer_class = ClothRollSerializer

    def get_queryset(self):
        qs = ClothRoll.objects.select_related("loft").all()
        loft_id = self.request.query_params.get("loftId")
        status_ = self.request.query_params.get("status")
        if loft_id:
            qs = qs.filter(loft_id=loft_id)
        if status_:
            qs = qs.filter(status=status_)
        return qs


class DipRunViewSet(viewsets.ModelViewSet):
    serializer_class = DipRunSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = DipRun.objects.select_related("roll", "roll__loft").all()
        roll_id = self.request.query_params.get("rollId")
        if roll_id:
            qs = qs.filter(roll_id=roll_id)
        return qs


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    data = {
        "loftCount": Loft.objects.count(),
        "rawRollCount": ClothRoll.objects.filter(status=ClothRoll.STATUS_RAW).count(),
        "dippingRollCount": ClothRoll.objects.filter(
            status=ClothRoll.STATUS_DIPPING
        ).count(),
        "curedRollCount": ClothRoll.objects.filter(status=ClothRoll.STATUS_CURED).count(),
        "dipRunCount": DipRun.objects.count(),
    }
    return Response(data)
