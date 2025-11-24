import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
from datetime import datetime
from typing import List
from pathlib import Path
from config.settings import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications"""
    
    def __init__(self):
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_username = settings.smtp_username
        self.smtp_password = settings.smtp_password
        self.from_email = settings.smtp_from_email
        self.from_name = settings.smtp_from_name
        
        # Load HTML template
        self.template_dir = Path(settings.email_template_dir)
        self.html_template_path = self.template_dir / settings.email_html_template
        self._load_template()
    
    def _load_template(self):
        """Load HTML email template from file"""
        if not self.html_template_path.exists():
            raise FileNotFoundError(
                f"Email template not found: {self.html_template_path}. "
                f"Please ensure the template file exists in the templates directory."
            )
        
        try:
            with open(self.html_template_path, 'r', encoding='utf-8') as f:
                self.html_template = f.read()
            logger.info(f"HTML template loaded from {self.html_template_path}")
        except Exception as e:
            logger.error(f"Error loading HTML template: {e}")
            raise
    
    def send_suspicious_event_notification(
        self,
        camera_id: str,
        detected_at: datetime,
        video_url: str,
        recipients: List[str] = None
    ) -> bool:
        """
        Send email notification about suspicious event
        
        Args:
            event_id: Unique event identifier
            camera_id: Camera that detected the event
            detected_at: When the event was detected
            video_url: URL to the video recording
            recipients: List of email recipients (uses default if None)
            
        Returns:
            bool: True if email was sent successfully
        """
        if recipients is None:
            recipients = settings.recipients_list
        
        if not recipients:
            logger.warning("No recipients configured for email notifications")
            return False
        
        subject = f"⚠️ Suspicious Activity Detected - {camera_id}"
        
        # Format detected time
        detected_time_str = detected_at.strftime("%Y-%m-%d %H:%M:%S")
        
        # Prepare template variables
        template_vars = {
            'detected_time': detected_time_str,
            'camera_id': camera_id,
            'video_url': video_url
        }
        
        # Render HTML template
        html_body = self.html_template
        for key, value in template_vars.items():
            html_body = html_body.replace(f'{{{{ {key} }}}}', str(value))
        
        return self._send_email(recipients, subject, html_body)
    
    def _send_email(
        self,
        recipients: List[str],
        subject: str,
        html_body: str
    ) -> bool:
        """
        Internal method to send email via SMTP
        
        Args:
            recipients: List of recipient email addresses
            subject: Email subject
            html_body: HTML version of email body
            
        Returns:
            bool: True if email was sent successfully
        """
        try:
            # Create message
            message = MIMEMultipart('alternative')
            message['From'] = f"{self.from_name} <{self.from_email}>"
            message['To'] = ', '.join(recipients)
            message['Subject'] = subject
            message['Date'] = formatdate(localtime=True)
            
            # Attach HTML version
            html_part = MIMEText(html_body, 'html')
            message.attach(html_part)
            
            # Connect to SMTP server and send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(message)
            
            logger.info(f"Email notification sent successfully to {len(recipients)} recipient(s)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}", exc_info=True)
            return False

