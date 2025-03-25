class GeoRouter:
    """
    A router to control all database operations on models in the rent_control app.
    """
    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'rent_control':
            return 'geodb'
        return 'default'

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'rent_control':
            return 'geodb'
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        # Objects in the same db can have relations
        if obj1._meta.app_label == obj2._meta.app_label:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Critical part: Only allow rent_control models in geodb
        if db == 'geodb':
            return app_label == 'rent_control'
        # All other models go to default db only
        elif db == 'default':
            return app_label != 'rent_control'
        return None