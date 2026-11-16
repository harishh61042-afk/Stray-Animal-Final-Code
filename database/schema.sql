-- PawConnect database schema (MySQL 8.0 or newer, InnoDB, utf8mb4)
--
-- Generated from the models in app/models by tools/make_schema.py. Do not edit it by hand:
-- change a model, then run  python tools/make_schema.py  again.
--
-- You normally do not need this file: `python init_db.py` creates the same tables and the default
-- administrator for you. Use it only if you prefer to create the tables yourself:
--     mysql -u root -p < database/schema.sql
-- It creates empty tables only (no accounts) and never drops or changes existing tables.
-- Tables: 22

CREATE DATABASE IF NOT EXISTS `pawconnect_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `pawconnect_db`;

-- users
CREATE TABLE IF NOT EXISTS `users` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `email` VARCHAR(120) NOT NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  `full_name` VARCHAR(100) NOT NULL,
  `phone` VARCHAR(20) NULL,
  `role` VARCHAR(20) NOT NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'active',
  `verification_status` VARCHAR(20) NOT NULL DEFAULT 'Not Required',
  `verification_note` TEXT NULL,
  `verified_at` DATETIME NULL,
  `verified_by` INT NULL,
  `must_change_password` TINYINT(1) NOT NULL DEFAULT 0,
  `failed_login_attempts` INT NOT NULL DEFAULT 0,
  `locked_until` DATETIME NULL,
  `last_login_at` DATETIME NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `updated_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_users_email` (`email`),
  KEY `ix_users_role` (`role`),
  KEY `ix_users_status` (`status`),
  CONSTRAINT `fk_users_verified_by` FOREIGN KEY (`verified_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- animal_reports
CREATE TABLE IF NOT EXISTS `animal_reports` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `report_code` VARCHAR(30) NOT NULL,
  `reporter_id` INT NULL,
  `reporter_name` VARCHAR(100) NOT NULL,
  `reporter_phone` VARCHAR(20) NOT NULL,
  `reporter_email` VARCHAR(120) NULL,
  `animal_type` VARCHAR(30) NOT NULL,
  `animal_description` TEXT NOT NULL,
  `approximate_age` VARCHAR(50) NULL,
  `animal_condition` VARCHAR(60) NOT NULL,
  `emergency_level` VARCHAR(20) NOT NULL DEFAULT 'Medium',
  `animal_count` INT NOT NULL DEFAULT 1,
  `image_filename` VARCHAR(255) NULL,
  `location_name` VARCHAR(150) NOT NULL,
  `address` TEXT NOT NULL,
  `latitude` DOUBLE NULL,
  `longitude` DOUBLE NULL,
  `additional_info` TEXT NULL,
  `status` VARCHAR(30) NOT NULL DEFAULT 'Pending',
  `rejection_reason` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `updated_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `closed_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_animal_reports_report_code` (`report_code`),
  KEY `ix_animal_reports_reporter_id` (`reporter_id`),
  KEY `ix_animal_reports_animal_type` (`animal_type`),
  KEY `ix_animal_reports_emergency_level` (`emergency_level`),
  KEY `ix_animal_reports_location_name` (`location_name`),
  KEY `ix_animal_reports_status` (`status`),
  KEY `ix_animal_reports_created_at` (`created_at`),
  CONSTRAINT `fk_animal_reports_reporter_id` FOREIGN KEY (`reporter_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- shelter_profiles
CREATE TABLE IF NOT EXISTS `shelter_profiles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL,
  `shelter_name` VARCHAR(150) NOT NULL,
  `registration_number` VARCHAR(60) NULL,
  `address` TEXT NULL,
  `city` VARCHAR(80) NULL,
  `state` VARCHAR(80) NULL,
  `pincode` VARCHAR(10) NULL,
  `latitude` DOUBLE NULL,
  `longitude` DOUBLE NULL,
  `contact_phone` VARCHAR(20) NULL,
  `contact_email` VARCHAR(120) NULL,
  `website` VARCHAR(200) NULL,
  `capacity` INT NOT NULL DEFAULT 20,
  `description` TEXT NULL,
  `verification_details` TEXT NULL,
  `verification_document` VARCHAR(255) NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `updated_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_shelter_profiles_user_id` (`user_id`),
  KEY `ix_shelter_profiles_shelter_name` (`shelter_name`),
  KEY `ix_shelter_profiles_city` (`city`),
  CONSTRAINT `fk_shelter_profiles_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- animals
CREATE TABLE IF NOT EXISTS `animals` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `animal_code` VARCHAR(30) NOT NULL,
  `name` VARCHAR(80) NULL,
  `animal_type` VARCHAR(30) NOT NULL,
  `breed` VARCHAR(80) NULL,
  `age_months` INT NULL,
  `gender` VARCHAR(10) NOT NULL DEFAULT 'Unknown',
  `color` VARCHAR(60) NULL,
  `description` TEXT NULL,
  `temperament` VARCHAR(200) NULL,
  `rescue_date` DATE NULL,
  `rescue_location` VARCHAR(200) NULL,
  `latitude` DOUBLE NULL,
  `longitude` DOUBLE NULL,
  `report_id` INT NULL,
  `shelter_id` INT NULL,
  `veterinarian_id` INT NULL,
  `rescuer_id` INT NULL,
  `registered_by` INT NULL,
  `health_condition` TEXT NULL,
  `vaccination_status` VARCHAR(30) NOT NULL DEFAULT 'Not Vaccinated',
  `medical_status` VARCHAR(30) NOT NULL DEFAULT 'Under Observation',
  `rehabilitation_status` VARCHAR(30) NOT NULL DEFAULT 'Not Started',
  `rehabilitation_notes` TEXT NULL,
  `status` VARCHAR(30) NOT NULL DEFAULT 'Rescued',
  `available_since` DATETIME NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `updated_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_animals_animal_code` (`animal_code`),
  KEY `ix_animals_name` (`name`),
  KEY `ix_animals_animal_type` (`animal_type`),
  KEY `ix_animals_report_id` (`report_id`),
  KEY `ix_animals_shelter_id` (`shelter_id`),
  KEY `ix_animals_veterinarian_id` (`veterinarian_id`),
  KEY `ix_animals_medical_status` (`medical_status`),
  KEY `ix_animals_status` (`status`),
  KEY `ix_animals_created_at` (`created_at`),
  CONSTRAINT `fk_animals_report_id` FOREIGN KEY (`report_id`) REFERENCES `animal_reports` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_animals_shelter_id` FOREIGN KEY (`shelter_id`) REFERENCES `shelter_profiles` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_animals_veterinarian_id` FOREIGN KEY (`veterinarian_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_animals_rescuer_id` FOREIGN KEY (`rescuer_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_animals_registered_by` FOREIGN KEY (`registered_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- adoption_applications
CREATE TABLE IF NOT EXISTS `adoption_applications` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `application_code` VARCHAR(30) NOT NULL,
  `animal_id` INT NOT NULL,
  `adopter_id` INT NOT NULL,
  `applicant_name` VARCHAR(100) NOT NULL,
  `applicant_email` VARCHAR(120) NOT NULL,
  `applicant_phone` VARCHAR(20) NOT NULL,
  `address` TEXT NOT NULL,
  `city` VARCHAR(80) NOT NULL,
  `state` VARCHAR(80) NULL,
  `pincode` VARCHAR(10) NULL,
  `occupation` VARCHAR(100) NULL,
  `housing_type` VARCHAR(40) NOT NULL,
  `household_members` INT NULL,
  `has_other_pets` TINYINT(1) NOT NULL DEFAULT 0,
  `other_pets_details` TEXT NULL,
  `previous_experience` TEXT NULL,
  `adoption_reason` TEXT NOT NULL,
  `agreed_to_terms` TINYINT(1) NOT NULL DEFAULT 0,
  `status` VARCHAR(20) NOT NULL DEFAULT 'Pending',
  `review_comment` TEXT NULL,
  `reviewed_by` INT NULL,
  `reviewed_at` DATETIME NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `updated_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_adoption_applications_application_code` (`application_code`),
  KEY `ix_adoption_applications_adopter_id` (`adopter_id`),
  KEY `ix_adoption_applications_status` (`status`),
  KEY `ix_adoption_applications_created_at` (`created_at`),
  KEY `ix_adoption_applications_animal_status` (`animal_id`, `status`),
  CONSTRAINT `fk_adoption_applications_animal_id` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_adoption_applications_adopter_id` FOREIGN KEY (`adopter_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_adoption_applications_reviewed_by` FOREIGN KEY (`reviewed_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- adoption_records: Written once when an adoption is completed.
CREATE TABLE IF NOT EXISTS `adoption_records` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `application_id` INT NOT NULL,
  `animal_id` INT NOT NULL,
  `adopter_id` INT NOT NULL,
  `shelter_id` INT NULL,
  `adoption_date` DATE NOT NULL,
  `completed_by` INT NULL,
  `final_notes` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_adoption_records_application_id` (`application_id`),
  UNIQUE KEY `uq_adoption_records_animal_id` (`animal_id`),
  KEY `ix_adoption_records_adopter_id` (`adopter_id`),
  KEY `ix_adoption_records_shelter_id` (`shelter_id`),
  CONSTRAINT `fk_adoption_records_application_id` FOREIGN KEY (`application_id`) REFERENCES `adoption_applications` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_adoption_records_animal_id` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_adoption_records_adopter_id` FOREIGN KEY (`adopter_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_adoption_records_shelter_id` FOREIGN KEY (`shelter_id`) REFERENCES `shelter_profiles` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_adoption_records_completed_by` FOREIGN KEY (`completed_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- animal_images
CREATE TABLE IF NOT EXISTS `animal_images` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `animal_id` INT NOT NULL,
  `filename` VARCHAR(255) NOT NULL,
  `caption` VARCHAR(200) NULL,
  `is_primary` TINYINT(1) NOT NULL DEFAULT 0,
  `uploaded_by` INT NULL,
  `uploaded_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  KEY `ix_animal_images_animal_id` (`animal_id`),
  CONSTRAINT `fk_animal_images_animal_id` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_animal_images_uploaded_by` FOREIGN KEY (`uploaded_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- animal_status_history: Audit trail of every status change an animal goes through.
CREATE TABLE IF NOT EXISTS `animal_status_history` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `animal_id` INT NOT NULL,
  `old_status` VARCHAR(30) NULL,
  `new_status` VARCHAR(30) NOT NULL,
  `changed_by` INT NULL,
  `note` TEXT NULL,
  `changed_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  KEY `ix_animal_status_history_animal_id` (`animal_id`),
  CONSTRAINT `fk_animal_status_history_animal_id` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_animal_status_history_changed_by` FOREIGN KEY (`changed_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- shelter_admissions: Admission / accommodation record: when an animal entered and left a shelter.
CREATE TABLE IF NOT EXISTS `shelter_admissions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `shelter_id` INT NOT NULL,
  `animal_id` INT NOT NULL,
  `admitted_by` INT NULL,
  `admitted_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `discharged_at` DATETIME NULL,
  `discharge_reason` VARCHAR(60) NULL,
  `capacity_override` TINYINT(1) NOT NULL DEFAULT 0,
  `override_reason` TEXT NULL,
  `note` TEXT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_shelter_admissions_animal_id` (`animal_id`),
  KEY `ix_shelter_admissions_shelter_discharged` (`shelter_id`, `discharged_at`),
  CONSTRAINT `fk_shelter_admissions_shelter_id` FOREIGN KEY (`shelter_id`) REFERENCES `shelter_profiles` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_shelter_admissions_animal_id` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_shelter_admissions_admitted_by` FOREIGN KEY (`admitted_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- medical_records
CREATE TABLE IF NOT EXISTS `medical_records` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `animal_id` INT NOT NULL,
  `veterinarian_id` INT NOT NULL,
  `created_by` INT NULL,
  `updated_by` INT NULL,
  `examination_date` DATE NOT NULL,
  `weight_kg` FLOAT NULL,
  `symptoms` TEXT NULL,
  `diagnosis` TEXT NOT NULL,
  `treatment` TEXT NULL,
  `medicines` TEXT NULL,
  `medical_status` VARCHAR(30) NOT NULL DEFAULT 'Under Observation',
  `notes` TEXT NULL,
  `follow_up_date` DATE NULL,
  `document_filename` VARCHAR(255) NULL,
  `document_original_name` VARCHAR(255) NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `updated_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  KEY `ix_medical_records_veterinarian_id` (`veterinarian_id`),
  KEY `ix_medical_records_follow_up_date` (`follow_up_date`),
  KEY `ix_medical_records_animal_date` (`animal_id`, `examination_date`),
  CONSTRAINT `fk_medical_records_animal_id` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_medical_records_veterinarian_id` FOREIGN KEY (`veterinarian_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_medical_records_created_by` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_medical_records_updated_by` FOREIGN KEY (`updated_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- vaccinations
CREATE TABLE IF NOT EXISTS `vaccinations` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `animal_id` INT NOT NULL,
  `medical_record_id` INT NULL,
  `vaccine_name` VARCHAR(120) NOT NULL,
  `vaccination_date` DATE NOT NULL,
  `next_due_date` DATE NULL,
  `administered_by` INT NULL,
  `batch_number` VARCHAR(60) NULL,
  `notes` TEXT NULL,
  `reminder_sent` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  KEY `ix_vaccinations_animal_id` (`animal_id`),
  KEY `ix_vaccinations_next_due_date` (`next_due_date`),
  CONSTRAINT `fk_vaccinations_animal_id` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_vaccinations_medical_record_id` FOREIGN KEY (`medical_record_id`) REFERENCES `medical_records` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_vaccinations_administered_by` FOREIGN KEY (`administered_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- user_profiles: Optional personal details shared by every role.
CREATE TABLE IF NOT EXISTS `user_profiles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL,
  `address` TEXT NULL,
  `city` VARCHAR(80) NULL,
  `state` VARCHAR(80) NULL,
  `pincode` VARCHAR(10) NULL,
  `date_of_birth` DATE NULL,
  `bio` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `updated_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_profiles_user_id` (`user_id`),
  CONSTRAINT `fk_user_profiles_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- volunteer_profiles
CREATE TABLE IF NOT EXISTS `volunteer_profiles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL,
  `skills` TEXT NULL,
  `experience` TEXT NULL,
  `availability` VARCHAR(200) NULL,
  `motivation` TEXT NULL,
  `emergency_contact_name` VARCHAR(100) NULL,
  `emergency_contact_phone` VARCHAR(20) NULL,
  `application_status` VARCHAR(20) NOT NULL DEFAULT 'Pending',
  `applied_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `reviewed_by` INT NULL,
  `reviewed_at` DATETIME NULL,
  `review_note` TEXT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_volunteer_profiles_user_id` (`user_id`),
  KEY `ix_volunteer_profiles_application_status` (`application_status`),
  CONSTRAINT `fk_volunteer_profiles_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_volunteer_profiles_reviewed_by` FOREIGN KEY (`reviewed_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- rescuer_profiles
CREATE TABLE IF NOT EXISTS `rescuer_profiles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL,
  `organization` VARCHAR(150) NULL,
  `experience_years` INT NULL,
  `service_area` VARCHAR(150) NULL,
  `has_vehicle` TINYINT(1) NOT NULL DEFAULT 0,
  `verification_details` TEXT NULL,
  `verification_document` VARCHAR(255) NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `updated_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rescuer_profiles_user_id` (`user_id`),
  CONSTRAINT `fk_rescuer_profiles_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- veterinarian_profiles
CREATE TABLE IF NOT EXISTS `veterinarian_profiles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL,
  `clinic_name` VARCHAR(150) NULL,
  `license_number` VARCHAR(60) NULL,
  `specialization` VARCHAR(100) NULL,
  `qualification` VARCHAR(150) NULL,
  `experience_years` INT NULL,
  `clinic_address` TEXT NULL,
  `consultation_hours` VARCHAR(100) NULL,
  `verification_details` TEXT NULL,
  `verification_document` VARCHAR(255) NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `updated_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_veterinarian_profiles_user_id` (`user_id`),
  CONSTRAINT `fk_veterinarian_profiles_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- rescue_assignments: A rescuer assigned to a report. A report may be reassigned several times.
CREATE TABLE IF NOT EXISTS `rescue_assignments` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `report_id` INT NOT NULL,
  `rescuer_id` INT NOT NULL,
  `assigned_by` INT NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'Assigned',
  `deadline` DATETIME NULL,
  `instructions` TEXT NULL,
  `response_note` TEXT NULL,
  `assigned_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `responded_at` DATETIME NULL,
  `completed_at` DATETIME NULL,
  `completion_details` TEXT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_rescue_assignments_report_status` (`report_id`, `status`),
  KEY `ix_rescue_assignments_rescuer_status` (`rescuer_id`, `status`),
  CONSTRAINT `fk_rescue_assignments_report_id` FOREIGN KEY (`report_id`) REFERENCES `animal_reports` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_rescue_assignments_rescuer_id` FOREIGN KEY (`rescuer_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_rescue_assignments_assigned_by` FOREIGN KEY (`assigned_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- rescue_activities: One entry in a report's history (status change, note, assignment ...).
CREATE TABLE IF NOT EXISTS `rescue_activities` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `report_id` INT NOT NULL,
  `actor_id` INT NULL,
  `activity_type` VARCHAR(40) NOT NULL,
  `old_status` VARCHAR(30) NULL,
  `new_status` VARCHAR(30) NULL,
  `note` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  KEY `ix_rescue_activities_report_created` (`report_id`, `created_at`),
  CONSTRAINT `fk_rescue_activities_report_id` FOREIGN KEY (`report_id`) REFERENCES `animal_reports` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_rescue_activities_actor_id` FOREIGN KEY (`actor_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- notifications
CREATE TABLE IF NOT EXISTS `notifications` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL,
  `title` VARCHAR(150) NOT NULL,
  `message` TEXT NOT NULL,
  `category` VARCHAR(30) NOT NULL DEFAULT 'system',
  `link_url` VARCHAR(255) NULL,
  `is_read` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `read_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  KEY `ix_notifications_user_read_created` (`user_id`, `is_read`, `created_at`),
  CONSTRAINT `fk_notifications_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- audit_logs: System activity: who did what, and when.
CREATE TABLE IF NOT EXISTS `audit_logs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NULL,
  `action` VARCHAR(60) NOT NULL,
  `entity_type` VARCHAR(40) NULL,
  `entity_id` INT NULL,
  `description` TEXT NULL,
  `ip_address` VARCHAR(45) NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  KEY `ix_audit_logs_user_id` (`user_id`),
  KEY `ix_audit_logs_action` (`action`),
  KEY `ix_audit_logs_created_at` (`created_at`),
  CONSTRAINT `fk_audit_logs_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- contact_messages: Messages sent through the public contact form.
CREATE TABLE IF NOT EXISTS `contact_messages` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL,
  `email` VARCHAR(120) NOT NULL,
  `subject` VARCHAR(150) NOT NULL,
  `message` TEXT NOT NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'New',
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  PRIMARY KEY (`id`),
  KEY `ix_contact_messages_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- volunteer_tasks
CREATE TABLE IF NOT EXISTS `volunteer_tasks` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `title` VARCHAR(150) NOT NULL,
  `description` TEXT NULL,
  `task_type` VARCHAR(60) NOT NULL,
  `location_name` VARCHAR(150) NULL,
  `address` TEXT NULL,
  `latitude` DOUBLE NULL,
  `longitude` DOUBLE NULL,
  `instructions` TEXT NULL,
  `due_at` DATETIME NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'Available',
  `volunteers_needed` INT NOT NULL DEFAULT 1,
  `report_id` INT NULL,
  `animal_id` INT NULL,
  `shelter_id` INT NULL,
  `created_by` INT NULL,
  `cancel_reason` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `updated_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `completed_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  KEY `ix_volunteer_tasks_task_type` (`task_type`),
  KEY `ix_volunteer_tasks_status` (`status`),
  KEY `ix_volunteer_tasks_report_id` (`report_id`),
  CONSTRAINT `fk_volunteer_tasks_report_id` FOREIGN KEY (`report_id`) REFERENCES `animal_reports` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_volunteer_tasks_animal_id` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_volunteer_tasks_shelter_id` FOREIGN KEY (`shelter_id`) REFERENCES `shelter_profiles` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_volunteer_tasks_created_by` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- volunteer_task_assignments
CREATE TABLE IF NOT EXISTS `volunteer_task_assignments` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `task_id` INT NOT NULL,
  `volunteer_id` INT NOT NULL,
  `assigned_by` INT NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'Assigned',
  `progress_percent` INT NOT NULL DEFAULT 0,
  `progress_note` TEXT NULL,
  `assigned_at` DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `responded_at` DATETIME NULL,
  `started_at` DATETIME NULL,
  `completed_at` DATETIME NULL,
  `hours_spent` FLOAT NULL,
  `completion_notes` TEXT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_volunteer_task_assignments_task_id` (`task_id`),
  KEY `ix_volunteer_task_assignments_volunteer_id` (`volunteer_id`),
  KEY `ix_volunteer_task_assignments_status` (`status`),
  UNIQUE KEY `uq_task_volunteer` (`task_id`, `volunteer_id`),
  CONSTRAINT `fk_volunteer_task_assignments_task_id` FOREIGN KEY (`task_id`) REFERENCES `volunteer_tasks` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_volunteer_task_assignments_volunteer_id` FOREIGN KEY (`volunteer_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_volunteer_task_assignments_assigned_by` FOREIGN KEY (`assigned_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
