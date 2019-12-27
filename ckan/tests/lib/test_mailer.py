# encoding: utf-8

import base64
import hashlib
import pytest
from email.header import decode_header
from email.mime.text import MIMEText
from email.parser import Parser

import ckan.lib.helpers as h
import ckan.lib.mailer as mailer
import ckan.model as model
import ckan.tests.factories as factories
import ckan.tests.helpers as helpers
from ckan.common import config
from ckan.tests.legacy.mock_mail_server import SmtpServerHarness


class MailerBase(SmtpServerHarness):
    @classmethod
    def setup_class(cls):

        helpers.reset_db()

        smtp_server = config.get("smtp.test_server")
        if smtp_server:
            host, port = smtp_server.split(":")
            port = int(port) + int(
                str(hashlib.md5(cls.__name__).hexdigest())[0], 16
            )
            config["smtp.test_server"] = "%s:%s" % (host, port)

        # Created directly to avoid email validation
        user_without_email = model.User(name="mary", email=None)
        model.Session.add(user_without_email)
        model.Session.commit()
        SmtpServerHarness.setup_class()

    @classmethod
    def teardown_class(cls):
        SmtpServerHarness.teardown_class()
        helpers.reset_db()

    def setup(self):
        self.clear_smtp_messages()

    def mime_encode(self, msg, recipient_name):
        text = MIMEText(msg.encode("utf-8"), "plain", "utf-8")
        encoded_body = text.get_payload().strip()
        return encoded_body

    def get_email_body(self, msg):
        payload = Parser().parsestr(msg).get_payload()
        return base64.b64decode(payload)

    def get_email_subject(self, msg):
        header = Parser().parsestr(msg)["Subject"]
        return decode_header(header)[0][0]


class TestMailer(MailerBase):
    def test_mail_recipient(self):
        user = factories.User()

        msgs = self.get_smtp_messages()
        assert msgs == []

        # send email
        test_email = {
            "recipient_name": "Bob",
            "recipient_email": user["email"],
            "subject": "Meeting",
            "body": "The meeting is cancelled.",
            "headers": {"header1": "value1"},
        }
        mailer.mail_recipient(**test_email)

        # check it went to the mock smtp server
        msgs = self.get_smtp_messages()
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg[1] == config["smtp.mail_from"]
        assert msg[2] == [test_email["recipient_email"]]
        assert test_email["headers"].keys()[0] in msg[3], msg[3]
        assert test_email["headers"].values()[0] in msg[3], msg[3]
        assert test_email["subject"] in msg[3], msg[3]
        expected_body = self.mime_encode(
            test_email["body"], test_email["recipient_name"]
        )
        assert expected_body in msg[3]

    def test_mail_user(self):

        user = factories.User()
        user_obj = model.User.by_name(user["name"])

        msgs = self.get_smtp_messages()
        assert msgs == []

        # send email
        test_email = {
            "recipient": user_obj,
            "subject": "Meeting",
            "body": "The meeting is cancelled.",
            "headers": {"header1": "value1"},
        }
        mailer.mail_user(**test_email)

        # check it went to the mock smtp server
        msgs = self.get_smtp_messages()
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg[1] == config["smtp.mail_from"]
        assert msg[2] == [user["email"]]
        assert test_email["headers"].keys()[0] in msg[3], msg[3]
        assert test_email["headers"].values()[0] in msg[3], msg[3]
        assert test_email["subject"] in msg[3], msg[3]
        expected_body = self.mime_encode(test_email["body"], user["name"])

        assert expected_body in msg[3]

    def test_mail_user_without_email(self):
        # send email
        test_email = {
            "recipient": model.User.by_name(u"mary"),
            "subject": "Meeting",
            "body": "The meeting is cancelled.",
            "headers": {"header1": "value1"},
        }
        with pytest.raises(mailer.MailerException):
            mailer.mail_user(**test_email)

    @helpers.change_config("ckan.site_title", "My CKAN instance")
    def test_from_field_format(self):

        msgs = self.get_smtp_messages()
        assert msgs == []

        # send email
        test_email = {
            "recipient_name": "Bob",
            "recipient_email": "Bob@bob.com",
            "subject": "Meeting",
            "body": "The meeting is cancelled.",
            "headers": {"header1": "value1"},
        }
        mailer.mail_recipient(**test_email)

        # check it went to the mock smtp server
        msgs = self.get_smtp_messages()
        msg = msgs[0]

        expected_from_header = "{0} <{1}>".format(
            config.get("ckan.site_title"), config.get("smtp.mail_from")
        )

        assert expected_from_header in msg[3]

    def test_send_reset_email(self):
        user = factories.User()
        user_obj = model.User.by_name(user["name"])

        mailer.send_reset_link(user_obj)

        # check it went to the mock smtp server
        msgs = self.get_smtp_messages()
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg[1] == config["smtp.mail_from"]
        assert msg[2] == [user["email"]]
        assert "Reset" in msg[3], msg[3]
        test_msg = mailer.get_reset_link_body(user_obj)
        expected_body = self.mime_encode(test_msg, user["name"])

        assert expected_body in msg[3]

    def test_send_invite_email(self):
        user = factories.User()
        user_obj = model.User.by_name(user["name"])
        assert user_obj.reset_key is None, user_obj

        # send email
        mailer.send_invite(user_obj)

        # check it went to the mock smtp server
        msgs = self.get_smtp_messages()
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg[1] == config["smtp.mail_from"]
        assert msg[2] == [user["email"]]
        test_msg = mailer.get_invite_body(user_obj)
        expected_body = self.mime_encode(test_msg, user["name"])

        assert expected_body in msg[3]
        assert user_obj.reset_key is not None, user

    def test_send_invite_email_with_group(self):
        user = factories.User()
        user_obj = model.User.by_name(user["name"])

        group = factories.Group()
        role = "member"

        # send email
        mailer.send_invite(user_obj, group_dict=group, role=role)

        # check it went to the mock smtp server
        msgs = self.get_smtp_messages()
        msg = msgs[0]
        body = self.get_email_body(msg[3])
        assert group["title"] in body
        assert h.roles_translated()[role] in body

    def test_send_invite_email_with_org(self):
        user = factories.User()
        user_obj = model.User.by_name(user["name"])

        org = factories.Organization()
        role = "admin"

        # send email
        mailer.send_invite(user_obj, group_dict=org, role=role)

        # check it went to the mock smtp server
        msgs = self.get_smtp_messages()
        msg = msgs[0]
        body = self.get_email_body(msg[3])
        assert org["title"] in body
        assert h.roles_translated()[role] in body

    @helpers.change_config("smtp.test_server", "999.999.999.999")
    def test_bad_smtp_host(self):
        test_email = {
            "recipient_name": "Bob",
            "recipient_email": "b@example.com",
            "subject": "Meeting",
            "body": "The meeting is cancelled.",
            "headers": {"header1": "value1"},
        }
        with pytest.raises(mailer.MailerException):
            mailer.mail_recipient(**test_email)

    @helpers.change_config("smtp.reply_to", "norply@ckan.org")
    def test_reply_to(self):

        msgs = self.get_smtp_messages()
        assert msgs == []

        # send email
        test_email = {
            "recipient_name": "Bob",
            "recipient_email": "Bob@bob.com",
            "subject": "Meeting",
            "body": "The meeting is cancelled.",
            "headers": {"header1": "value1"},
        }
        mailer.mail_recipient(**test_email)

        # check it went to the mock smtp server
        msgs = self.get_smtp_messages()
        msg = msgs[0]

        expected_from_header = "Reply-to: {}".format(
            config.get("smtp.reply_to")
        )

        assert expected_from_header in msg[3]
