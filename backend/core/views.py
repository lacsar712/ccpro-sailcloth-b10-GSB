from django.db import IntegrityError, transaction
from django.db.models import Count
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsAdminRole

from .models import ClothRoll, DipRun, Loft
from .serializers import ClothRollSerializer, DipRunSerializer, LoftSerializer


class RenameLoftSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)

    def validate_name(self, value):
        """新名不得为空白；统一去首尾空格后再比较。"""
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("帆布间名不得为空")
        return cleaned


class LoftViewSet(viewsets.ReadOnlyModelViewSet):
    """帆布间台账只读；改名走专属 rename 动作，仅管理员可用。

    刻意不开放 create/update/destroy：改名台只允许改间名，
    不允许顺手删帆布间（会级联删卷）或触碰任何布卷状态。
    """

    queryset = Loft.objects.annotate(roll_count=Count("rolls")).order_by("id")
    serializer_class = LoftSerializer

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsAdminRole])
    def rename(self, request, pk=None):
        loft = self.get_object()
        payload = RenameLoftSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        new_name = payload.validated_data["name"]

        if new_name == loft.name:
            return Response(self.get_serializer(loft).data)

        # 常规撞名在库外先拦一道，给出友好提示。
        if Loft.objects.filter(name=new_name).exists():
            raise serializers.ValidationError({"name": "该帆布间名已存在，两间不得撞名"})

        # 两名管理员交叉改同名时靠唯一约束兜底：只有一人提交成功。
        try:
            with transaction.atomic():
                loft.name = new_name
                loft.save(update_fields=["name"])
        except IntegrityError:
            raise serializers.ValidationError(
                {"name": "该帆布间名已存在，两间不得撞名"}
            )

        return Response(self.get_serializer(loft).data)


class ClothRollViewSet(viewsets.ModelViewSet):
    serializer_class = ClothRollSerializer

    def get_queryset(self):
        qs = ClothRoll.objects.select_related("loft").all()
        loft_id = self.request.query_params.get("loftId")
        status = self.request.query_params.get("status")
        if loft_id:
            qs = qs.filter(loft_id=loft_id)
        if status:
            qs = qs.filter(status=status)
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
