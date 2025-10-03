from django.urls import path, include, re_path
from . import views, views_guild, views_store, views_bans, views_houses, views_news, views_pix, views_updater
from django.contrib.auth import views as auth_views
from .views_bazaar import bazaar_list, bazaar_offer, bazaar_bid, bazaar_sell 


urlpatterns = [
    path('', views_news.news_list, name='home'),
    path('gallery/', views.gallery, name='gallery'), 
    path('highscores/', views.highscores, name='highscores'), 
    path("guilds/", views_guild.guild_list, name="guild_list"),
    path("guilds/<path:name>/", views_guild.guild_detail, name="guild_detail"),

    path("server_status/", views.server_status, name="server_status"), # JSON
    path("server_players/", views.server_players, name="server_players"),  # JSON
    #path("character/<str:name>/inventory.json", views.character_inventory_json, name="char_inventory_json"), # JSON
    path("character/<str:name>/inventory.json", views.character_inventory, name="character_inventory"),
    path("character/<str:name>/equipment.json", views.character_equipment, name="character_equipment"),
    path("character/<str:name>/depot.json", views.character_depot, name="character_depot"),
    
    path("community/search-character/", views.search_character, name="search_character"),
    path("character/<str:name>/", views.character_detail, name="character_detail"),
    
    path("online/", views.online_list, name="online_list"),       
    path("server_info/", views.server_info, name="server_info"),
    path("accounts/signup/", views.signup, name="signup"),  # add a signup
    path("accounts/signup/confirm/<uidb64>/<token>/", views.signup_confirm, name="signup_confirm"),


    path("bazaar/", bazaar_list, name="bazaar_list"),
    path("bazaar/sell/", bazaar_sell, name="bazaar_sell"),
    path("bazaar/<int:offer_id>/", bazaar_offer, name="bazaar_offer"),
    path("bazaar/<int:offer_id>/bid/", bazaar_bid, name="bazaar_bid"),

    
    path("account/", views.account_manage, name="account_manage"),
    path("account/characters/<int:pid>/edit/", views.account_character_edit, name="account_character_edit"),
    path("account/characters/<int:pid>/delete/", views.account_character_delete, name="account_character_delete"),
    path("account/create-character", views.account_character_create, name="account_character_create"),
    
    # authentication URLs
    path("accounts/password_reset/",
         auth_views.PasswordResetView.as_view(
             template_name="registration/reset_form.html"),
         name="password_reset"),
    path("accounts/password_reset/done/",
         auth_views.PasswordResetDoneView.as_view(
             template_name="registration/reset_done.html"),
         name="password_reset_done"),
    path("accounts/reset/<uidb64>/<token>/",
         auth_views.PasswordResetConfirmView.as_view(
             template_name="registration/reset_confirm.html"),
         name="password_reset_confirm"),
    path("accounts/reset/done/",
         auth_views.PasswordResetCompleteView.as_view(
             template_name="registration/reset_complete.html"),
         name="password_reset_complete"),

    path("accounts/password_change/",
         auth_views.PasswordChangeView.as_view(
             template_name="registration/change_form.html"),
         name="password_change"),
    path("accounts/password_change/done/",
         auth_views.PasswordChangeDoneView.as_view(
             template_name="registration/change_done.html"),
         name="password_change_done"),

    path("accounts/", include("django.contrib.auth.urls")),  # optional

    path("donate/", views_store.donate, name="donate"),

    # Stripe
    path("store/stripe/create-session/", views_store.create_checkout_session, name="store_create_checkout"),
    path("store/stripe/webhook/", views_store.stripe_webhook, name="store_stripe_webhook"),

    # PayPal
    path("store/paypal/create/", views_store.paypal_create, name="store_paypal_create"),
    path("store/paypal/capture/", views_store.paypal_capture, name="store_paypal_capture"),

    # PIX
    path("store/pix/create/", views_pix.pix_create, name="pix_create"),
    path("store/pix/status/<str:txid>/", views_pix.pix_status, name="pix_status"),
    path("store/pix/webhook/", views_pix.pix_webhook, name="pix_webhook"),

    # Results
    path("store/success/", views_store.store_success, name="store_success"),
    path("store/cancel/", views_store.store_cancel, name="store_cancel"),

    path("last-kills/", views.last_kills, name="last_kills"),
    path("team/", views.team, name="team"),
    path("bans/", views_bans.bans_list, name="bans_list"),
    path("houses/", views_houses.houses_list, name="houses_list"),
    path("house/<int:house_id>/", views_houses.house_detail, name="house_detail"),
    path("rules/", views.rules, name="rules"),
    path("commands/", views.commands, name="commands"),
    
    path("news/", views_news.news_list, name="news_list"),
    path("news/archive/", views_news.news_archive, name="news_archive"),
    path("news/<int:year>/<int:month>/", views_news.news_archive_month, name="news_archive_month"),
    path("news/<slug:slug>/", views_news.news_detail, name="news_detail"),
    path("tinymce/", include("tinymce.urls")),
    path("api/", views_updater.updater, name="otclient_updater"),
    re_path(r"^api/(?P<subpath>.+)$", views_updater.api_file, name="api"),
]