from ..field import admin_field_generator
from .. import html_tags


def image(verbose_name="", width_px=200, clickable=True):

    def function_changer(func, admin_inst, model_inst):
        """
        :param func: returns an AdminFormAjaxData object
        :param admin_inst:
        :param model_inst:
        :return: html string
        """

        image_link = func(admin_inst, model_inst)

        if not image_link:
            return ""

        image_html = "<img style='width:%spx' src='%s'/>" % (width_px, image_link)

        if clickable:
            href = image_link

            return html_tags.anchor_tag(image_html, href, target='_blank')

        return image_html

    return admin_field_generator(verbose_name=verbose_name, function_changer=function_changer, html=True)
