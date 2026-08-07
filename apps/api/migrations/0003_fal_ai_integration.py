# Generated for the fal-ai-video-integration change.

from django.db import migrations, models


def delete_gesture_jobs(apps, schema_editor):
    """Delete preexisting Job rows with job_type="gesture".

    "gesture" (photo-only, audio-less talking-head video) is removed as a
    supported capability: veed/fabric-1.0 always requires audio_url, so
    there is no code path left that can process these rows. All existing
    "gesture" Jobs are demo/test data with no production value — leaving
    them "orphaned" outside JOB_TYPE_CHOICES would make them visible via
    the API pointing at a handler that no longer exists (InvalidJobType at
    runtime on legacy data). Deleting them keeps the dataset consistent
    with the new choices. This is intentionally NOT reversible: the
    reverse migration is a no-op, deleted demo rows do not come back.
    """
    Job = apps.get_model("api", "Job")
    Job.objects.filter(job_type="gesture").delete()


def noop(apps, schema_editor):
    """Reverse of delete_gesture_jobs: intentionally does nothing.

    Deleted demo Job rows cannot be un-deleted; this is accepted per the
    change's rollback plan (see proposal.md).
    """


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0002_deepfake_features"),
    ]

    operations = [
        migrations.RunPython(delete_gesture_jobs, reverse_code=noop),
        migrations.AlterField(
            model_name="job",
            name="job_type",
            field=models.CharField(
                choices=[("voice", "Voz"), ("video", "Video")],
                default="voice",
                max_length=20,
            ),
        ),
        migrations.RemoveField(
            model_name="job",
            name="did_talk_id",
        ),
        migrations.AddField(
            model_name="job",
            name="fal_request_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
