from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        max_length=200,
        help_text="Starting location (city, address, or landmark) within the USA",
    )
    end = serializers.CharField(
        max_length=200,
        help_text="Destination location within the USA",
    )

    def validate_start(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("start location cannot be blank.")
        return value.strip()

    def validate_end(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("end location cannot be blank.")
        return value.strip()
