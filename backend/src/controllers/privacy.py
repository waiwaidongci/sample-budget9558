from src.services import privacy

def overview(db,study_id,user):
    return {'study_id':study_id,'budget':privacy.budget_view_for(db,study_id),
            'channels':privacy.list_channels(db,study_id),
            'releases':privacy.list_releases(db,study_id,user.role),
            'touch_count':privacy.touch_count(db,study_id)}

def set_budget(db,study_id,data,user): return privacy.set_total_budget(db,study_id,data.total_epsilon,user)
def add_channel(db,study_id,data,user): return privacy.register_channel(db,study_id,data.name,user)
def delete_channel(db,study_id,channel_id,user): return privacy.remove_channel(db,study_id,channel_id,user)
def touches(db,study_id,user): return privacy.list_touches(db,study_id)
def save_touch(db,study_id,data,user): return privacy.save_touch(db,study_id,data,user)
def delete_touch(db,study_id,touch_id,user): return privacy.remove_touch(db,study_id,touch_id,user)
def publish(db,study_id,data,user): return privacy.publish(db,study_id,data,user)
def release(db,release_id,user): return privacy.get(db,release_id,user.role)
def export(db,release_id,user): return privacy.export(db,release_id,user.role,user)
