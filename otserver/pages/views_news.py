from calendar import month_name
from django.core.paginator import Paginator
from django.db.models import Count
from django.db.models.functions import ExtractYear, ExtractMonth
from django.shortcuts import get_object_or_404, render
from .models import News

def _pager(request, qs, per_page=10):
    page = int(request.GET.get("page", 1) or 1)
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page)
    return page_obj, {
        "page": page_obj.number,
        "per_page": per_page,
        "total": paginator.count,
        "total_pages": paginator.num_pages,
        "has_prev": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
    }

def news_list(request):
    qs = News.objects.filter(is_published=True)
    page_obj, meta = _pager(request, qs, per_page=8)
    return render(request, "pages/news_list.html", {
        "posts": page_obj.object_list,
        "page_obj": page_obj,
        "page_meta": meta,
    })

def news_detail(request, slug):
    post = get_object_or_404(News, slug=slug, is_published=True)
    # For a simple “recent” sidebar
    recent = News.objects.filter(is_published=True).exclude(pk=post.pk)[:5]
    return render(request, "pages/news_detail.html", {
        "post": post,
        "recent": recent,
    })

def news_archive(request):
    # year-month counts
    rows = (News.objects
        .filter(is_published=True)
        .annotate(y=ExtractYear("published_at"), m=ExtractMonth("published_at"))
        .values("y", "m")
        .annotate(n=Count("id"))
        .order_by("-y", "-m"))

    # group by year
    archive = {}
    for r in rows:
        archive.setdefault(r["y"], []).append({
            "month": r["m"],
            "month_name": month_name[r["m"]],
            "count": r["n"],
        })

    # also show latest posts on the right, optional
    latest = News.objects.filter(is_published=True)[:8]

    return render(request, "pages/news_archive.html", {
        "archive": archive,     # dict: {year: [{month, month_name, count}, ...]}
        "latest": latest,
    })

def news_archive_month(request, year, month):
    qs = News.objects.filter(is_published=True,
                             published_at__year=year,
                             published_at__month=month)
    page_obj, meta = _pager(request, qs, per_page=10)
    return render(request, "pages/news_archive_month.html", {
        "year": year, "month": month, "month_name": month_name[month],
        "posts": page_obj.object_list,
        "page_obj": page_obj,
        "page_meta": meta,
    })
