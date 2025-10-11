from django.db import models


class TemplateType(models.TextChoices):
    VERIFY = 'verify-code', 'Verify'
    WITHDRAW_ACCEPTED = 'withdraw-accepted', 'Withdraw Accepted'
    WITHDRAW_REJECTED = 'withdraw-rejected', 'Withdraw Rejected'
    DISABLE_STAKING = 'disable-staking', 'Disable Staking'
    LEVELUP_ACCEPTED = 'levelup-accepted', 'Level Up Accepted'
    LEVELUP_REJECTED = 'levelup-rejected', 'Level Up Rejected'
    STAKING_ACTIVATED = 'staking-activated', 'Staking Activated'
    STAKING_FINISHED = 'staking-finished', 'Staking Finished'


class MeliPayamakTemplate(models.Model):
    template_type = models.CharField(
        max_length=50,
        choices=TemplateType.choices,
        unique=True,
        verbose_name="Template Type"
    )
    code = models.TextField(verbose_name="Template Code", )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "الگو ملی پیامک"
        verbose_name_plural = "الگو های ملی پیامک"
        ordering = ['template_type']

    def __str__(self):
        return f"{self.get_template_type_display()} Template"

    def clean(self):
        super().clean()

    @staticmethod
    def get_template_code(template_type: TemplateType):
        try:
            template = MeliPayamakTemplate.objects.get(template_type=template_type)
            return template.code
        except MeliPayamakTemplate.DoesNotExist:
            return None
