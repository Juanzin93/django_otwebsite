class OTServRouter:
    app_label = "otdata"  # choose an app label for your OT models

    def db_for_read(self, model, **hints):
        return "retrowar" if model._meta.app_label == self.app_label else None

    def db_for_write(self, model, **hints):
        # usually read-only; keep writes off unless you intend to edit OT DB
        return "retrowar" if model._meta.app_label == self.app_label else None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == self.app_label:
            return db == "retrowar"
        return db == "default"
