# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AccountBanHistory(models.Model):
    account = models.ForeignKey('Accounts', models.DO_NOTHING)
    reason = models.CharField(max_length=255)
    banned_at = models.BigIntegerField()
    expired_at = models.BigIntegerField()
    banned_by = models.ForeignKey('Players', models.DO_NOTHING, db_column='banned_by')

    class Meta:
        managed = False
        db_table = 'account_ban_history'


class AccountBans(models.Model):
    account = models.OneToOneField('Accounts', models.DO_NOTHING, primary_key=True)
    reason = models.CharField(max_length=255)
    banned_at = models.BigIntegerField()
    expires_at = models.BigIntegerField()
    banned_by = models.ForeignKey('Players', models.DO_NOTHING, db_column='banned_by')

    class Meta:
        managed = False
        db_table = 'account_bans'


class AccountViplist(models.Model):
    account_id = models.IntegerField(db_comment='id of account whose viplist entry it is')
    player_id = models.IntegerField(db_comment='id of target player of viplist entry')
    description = models.CharField(max_length=128)
    icon = models.PositiveIntegerField()
    notify = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'account_viplist'
        unique_together = (('account_id', 'player_id'),)


class Accounts(models.Model):
    id = models.IntegerField(primary_key=True)
    password = models.CharField(max_length=40)
    type = models.IntegerField()
    premdays = models.IntegerField()
    lastday = models.PositiveIntegerField()
    pubkey = models.CharField(max_length=255)
    privatekey = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    created = models.IntegerField()
    rlname = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    country = models.CharField(max_length=3)
    web_lastlogin = models.IntegerField()
    web_flags = models.IntegerField()
    email_hash = models.CharField(max_length=32)
    email_new = models.CharField(max_length=255)
    email_new_time = models.IntegerField()
    email_code = models.CharField(max_length=255)
    email_next = models.IntegerField()
    premium_points = models.IntegerField()
    email_verified = models.IntegerField()
    key = models.CharField(max_length=64)
    coins = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'accounts'


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.IntegerField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.IntegerField()
    is_active = models.IntegerField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class CharMarket(models.Model):
    char_id = models.IntegerField()
    auction_start = models.IntegerField()
    auction_end = models.IntegerField()
    current_bid = models.IntegerField()
    highest_bid_acc = models.IntegerField()
    seller_account = models.IntegerField()
    name = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'char_market'


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.PositiveSmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class GuildInvites(models.Model):
    player_id = models.IntegerField(primary_key=True)  # The composite primary key (player_id, guild_id) found, that is not supported. The first column is selected.
    guild_id = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'guild_invites'
        unique_together = (('player_id', 'guild_id'),)


class GuildMembership(models.Model):
    player_id = models.IntegerField(primary_key=True)
    guild_id = models.IntegerField()
    rank_id = models.IntegerField()
    nick = models.CharField(max_length=15)

    class Meta:
        managed = False
        db_table = 'guild_membership'


class GuildRanks(models.Model):
    guild_id = models.IntegerField(db_comment='guild')
    name = models.CharField(max_length=255, db_comment='rank name')
    level = models.IntegerField(db_comment='rank level - leader, vice, member, maybe something else')

    class Meta:
        managed = False
        db_table = 'guild_ranks'


class GuildWars(models.Model):
    guild1 = models.IntegerField()
    guild2 = models.IntegerField()
    name1 = models.CharField(max_length=255)
    name2 = models.CharField(max_length=255)
    status = models.IntegerField()
    started = models.BigIntegerField()
    ended = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'guild_wars'


class Guilds(models.Model):
    name = models.CharField(unique=True, max_length=255)
    ownerid = models.OneToOneField('Players', models.DO_NOTHING, db_column='ownerid')
    creationdata = models.IntegerField()
    motd = models.CharField(max_length=255)
    description = models.TextField()
    logo_name = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'guilds'


class GuildwarKills(models.Model):
    killer = models.CharField(max_length=50)
    target = models.CharField(max_length=50)
    killerguild = models.IntegerField()
    targetguild = models.IntegerField()
    warid = models.IntegerField()
    time = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'guildwar_kills'


class HouseLists(models.Model):
    house_id = models.IntegerField()
    listid = models.IntegerField()
    list = models.TextField()

    class Meta:
        managed = False
        db_table = 'house_lists'


class Houses(models.Model):
    owner = models.IntegerField()
    paid = models.PositiveIntegerField()
    warnings = models.IntegerField()
    name = models.CharField(max_length=255)
    rent = models.IntegerField()
    town_id = models.IntegerField()
    bid = models.IntegerField()
    bid_end = models.IntegerField()
    last_bid = models.IntegerField()
    highest_bidder = models.IntegerField()
    size = models.IntegerField()
    beds = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'houses'


class IpBans(models.Model):
    ip = models.PositiveIntegerField(primary_key=True)
    reason = models.CharField(max_length=255)
    banned_at = models.BigIntegerField()
    expires_at = models.BigIntegerField()
    banned_by = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'ip_bans'


class MyaacAccountActions(models.Model):
    account_id = models.IntegerField()
    ip = models.PositiveIntegerField()
    ipv6 = models.CharField(max_length=16)
    date = models.IntegerField()
    action = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'myaac_account_actions'


class MyaacAdminMenu(models.Model):
    name = models.CharField(max_length=255)
    page = models.CharField(max_length=255)
    ordering = models.IntegerField()
    flags = models.IntegerField()
    enabled = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_admin_menu'


class MyaacBugtracker(models.Model):
    account = models.CharField(max_length=255)
    type = models.IntegerField()
    status = models.IntegerField()
    text = models.TextField()
    id = models.IntegerField()
    subject = models.CharField(max_length=255)
    reply = models.IntegerField()
    who = models.IntegerField()
    uid = models.AutoField(primary_key=True)
    tag = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_bugtracker'


class MyaacChangelog(models.Model):
    body = models.CharField(max_length=500)
    type = models.IntegerField(db_comment='1 - added, 2 - removed, 3 - changed, 4 - fixed')
    where = models.IntegerField(db_comment='1 - server, 2 - site')
    date = models.IntegerField()
    player_id = models.IntegerField()
    hidden = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_changelog'


class MyaacConfig(models.Model):
    name = models.CharField(unique=True, max_length=30)
    value = models.CharField(max_length=1000)

    class Meta:
        managed = False
        db_table = 'myaac_config'


class MyaacFaq(models.Model):
    question = models.CharField(max_length=255)
    answer = models.CharField(max_length=1020)
    ordering = models.IntegerField()
    hidden = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_faq'


class MyaacForum(models.Model):
    first_post = models.IntegerField()
    last_post = models.IntegerField()
    section = models.IntegerField()
    replies = models.IntegerField()
    views = models.IntegerField()
    author_aid = models.IntegerField()
    author_guid = models.IntegerField()
    post_text = models.TextField()
    post_topic = models.CharField(max_length=255)
    post_smile = models.IntegerField()
    post_html = models.IntegerField()
    post_date = models.IntegerField()
    last_edit_aid = models.IntegerField()
    edit_date = models.IntegerField()
    post_ip = models.CharField(max_length=32)
    sticked = models.IntegerField()
    closed = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_forum'


class MyaacForumBoards(models.Model):
    name = models.CharField(max_length=32)
    description = models.CharField(max_length=255)
    ordering = models.IntegerField()
    guild = models.IntegerField()
    access = models.IntegerField()
    closed = models.IntegerField()
    hidden = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_forum_boards'


class MyaacGallery(models.Model):
    comment = models.CharField(max_length=255)
    image = models.CharField(max_length=255)
    thumb = models.CharField(max_length=255)
    author = models.CharField(max_length=50)
    ordering = models.IntegerField()
    hidden = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_gallery'


class MyaacMenu(models.Model):
    template = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    link = models.CharField(max_length=255)
    blank = models.IntegerField()
    color = models.CharField(max_length=6)
    category = models.IntegerField()
    ordering = models.IntegerField()
    enabled = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_menu'


class MyaacMonsters(models.Model):
    hidden = models.IntegerField()
    name = models.CharField(max_length=255)
    mana = models.IntegerField()
    exp = models.IntegerField()
    health = models.IntegerField()
    speed_lvl = models.IntegerField()
    use_haste = models.IntegerField()
    voices = models.TextField()
    immunities = models.CharField(max_length=255)
    summonable = models.IntegerField()
    convinceable = models.IntegerField()
    race = models.CharField(max_length=255)
    loot = models.TextField()

    class Meta:
        managed = False
        db_table = 'myaac_monsters'


class MyaacNews(models.Model):
    title = models.CharField(max_length=100)
    body = models.TextField()
    type = models.IntegerField(db_comment='1 - news, 2 - ticker, 3 - article')
    date = models.IntegerField()
    category = models.IntegerField()
    player_id = models.IntegerField()
    last_modified_by = models.IntegerField()
    last_modified_date = models.IntegerField()
    comments = models.CharField(max_length=50)
    article_text = models.CharField(max_length=300)
    article_image = models.CharField(max_length=100)
    hidden = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_news'


class MyaacNewsCategories(models.Model):
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=50)
    icon_id = models.IntegerField()
    hidden = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_news_categories'


class MyaacNotepad(models.Model):
    account_id = models.IntegerField()
    content = models.TextField()

    class Meta:
        managed = False
        db_table = 'myaac_notepad'


class MyaacPages(models.Model):
    name = models.CharField(unique=True, max_length=30)
    title = models.CharField(max_length=30)
    body = models.TextField()
    date = models.IntegerField()
    player_id = models.IntegerField()
    php = models.IntegerField(db_comment='0 - plain html, 1 - php')
    enable_tinymce = models.IntegerField(db_comment='1 - enabled, 0 - disabled')
    access = models.IntegerField()
    hidden = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_pages'


class MyaacSpells(models.Model):
    spell = models.CharField(max_length=255)
    name = models.CharField(unique=True, max_length=255)
    words = models.CharField(max_length=255)
    category = models.IntegerField(db_comment='1 - attack, 2 - healing, 3 - summon, 4 - supply, 5 - support')
    type = models.IntegerField(db_comment='1 - instant, 2 - conjure, 3 - rune')
    level = models.IntegerField()
    maglevel = models.IntegerField()
    mana = models.IntegerField()
    soul = models.IntegerField()
    conjure_id = models.IntegerField()
    conjure_count = models.IntegerField()
    reagent = models.IntegerField()
    item_id = models.IntegerField()
    premium = models.IntegerField()
    vocations = models.CharField(max_length=100)
    hidden = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_spells'


class MyaacVideos(models.Model):
    title = models.CharField(max_length=100)
    youtube_id = models.CharField(max_length=20)
    author = models.CharField(max_length=50)
    ordering = models.IntegerField()
    hidden = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'myaac_videos'


class MyaacVisitors(models.Model):
    ip = models.CharField(unique=True, max_length=45)
    lastvisit = models.IntegerField()
    page = models.CharField(max_length=2048)

    class Meta:
        managed = False
        db_table = 'myaac_visitors'


class MyaacWeapons(models.Model):
    id = models.IntegerField(primary_key=True)
    level = models.IntegerField()
    maglevel = models.IntegerField()
    vocations = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'myaac_weapons'


class PagesProfile(models.Model):
    id = models.BigAutoField(primary_key=True)
    ot_account_id = models.IntegerField(blank=True, null=True)
    user = models.OneToOneField(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'pages_profile'


class PlayerDeaths(models.Model):
    player_id = models.IntegerField()
    time = models.PositiveBigIntegerField()
    level = models.IntegerField()
    killed_by = models.CharField(max_length=255)
    is_player = models.IntegerField()
    mostdamage_by = models.CharField(max_length=100)
    mostdamage_is_player = models.IntegerField()
    unjustified = models.IntegerField()
    mostdamage_unjustified = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'player_deaths'

class PlayerMurders(models.Model):
    id = models.BigAutoField(primary_key=True)
    player_id = models.IntegerField()
    date = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'player_murders'


class PlayerNamelocks(models.Model):
    player_id = models.IntegerField(primary_key=True)
    reason = models.CharField(max_length=255)
    namelocked_at = models.BigIntegerField()
    namelocked_by = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'player_namelocks'


class PlayerSpells(models.Model):
    player_id = models.IntegerField()
    name = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'player_spells'


class PlayerStorage(models.Model):
    player_id = models.IntegerField(primary_key=True)  # The composite primary key (player_id, key) found, that is not supported. The first column is selected.
    key = models.PositiveIntegerField()
    value = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'player_storage'
        unique_together = (('player_id', 'key'),)


class Players(models.Model):
    name = models.CharField(unique=True, max_length=255)
    group_id = models.IntegerField()
    account_id = models.IntegerField()
    level = models.IntegerField()
    goldenarena = models.IntegerField(db_column='goldenArena')  # Field name made lowercase.
    vocation = models.IntegerField()
    health = models.IntegerField()
    healthmax = models.IntegerField()
    experience = models.BigIntegerField()
    dailyexp = models.BigIntegerField(db_column='dailyExp')  # Field name made lowercase.
    weeklyexp = models.BigIntegerField(db_column='weeklyExp')  # Field name made lowercase.
    monthlyexp = models.BigIntegerField(db_column='monthlyExp')  # Field name made lowercase.
    lookbody = models.IntegerField()
    lookfeet = models.IntegerField()
    lookhead = models.IntegerField()
    looklegs = models.IntegerField()
    looktype = models.IntegerField()
    lookaddons = models.IntegerField()
    maglevel = models.IntegerField()
    mana = models.IntegerField()
    manamax = models.IntegerField()
    manaspent = models.PositiveIntegerField()
    soul = models.PositiveIntegerField()
    town_id = models.IntegerField()
    posx = models.IntegerField()
    posy = models.IntegerField()
    posz = models.IntegerField()
    conditions = models.TextField()
    cap = models.IntegerField()
    sex = models.IntegerField()
    lastlogin = models.PositiveBigIntegerField()
    lastip = models.PositiveIntegerField()
    save = models.IntegerField()
    skull = models.IntegerField()
    skulltime = models.IntegerField()
    lastlogout = models.PositiveBigIntegerField()
    blessings = models.IntegerField()
    onlinetime = models.IntegerField()
    deletion = models.BigIntegerField()
    balance = models.PositiveBigIntegerField()
    skill_fist = models.PositiveIntegerField()
    skill_fist_tries = models.PositiveBigIntegerField()
    skill_club = models.PositiveIntegerField()
    skill_club_tries = models.PositiveBigIntegerField()
    skill_sword = models.PositiveIntegerField()
    skill_sword_tries = models.PositiveBigIntegerField()
    skill_axe = models.PositiveIntegerField()
    skill_axe_tries = models.PositiveBigIntegerField()
    skill_dist = models.PositiveIntegerField()
    skill_dist_tries = models.PositiveBigIntegerField()
    skill_shielding = models.PositiveIntegerField()
    skill_shielding_tries = models.PositiveBigIntegerField()
    skill_fishing = models.PositiveIntegerField()
    skill_fishing_tries = models.PositiveBigIntegerField()
    deleted = models.IntegerField()
    hwid = models.CharField(max_length=255)
    created = models.IntegerField()
    hidden = models.IntegerField()
    comment = models.TextField()

    class Meta:
        managed = False
        db_table = 'players'


class PlayersOnline(models.Model):
    player_id = models.IntegerField(primary_key=True)

    class Meta:
        managed = False
        db_table = 'players_online'


class ServerConfig(models.Model):
    config = models.CharField(primary_key=True, max_length=50)
    value = models.CharField(max_length=256)

    class Meta:
        managed = False
        db_table = 'server_config'


class TileStore(models.Model):
    house_id = models.IntegerField()
    data = models.TextField()
    abilities = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tile_store'
