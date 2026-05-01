from django.http import JsonResponse



def health_check(request):
    return JsonResponse({"healthy": True, "service": "darasa-core"})