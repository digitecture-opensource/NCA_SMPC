/* =======================================================================================
   IDMP PoC (MHRA/UK) – FINAL DDL
   - Controlled Vocabulary (RIM_CV) + Terms (CV_Term)
   - All coded FKs reference rim.CV_Term(TermID)
   - Denormalised text columns for reporting
   - Triggers maintain denorm columns:
       (a) when FK changes in domain tables
       (b) when term description changes in rim.CV_Term
   Notes:
   - Schema names used: rim, Master, CV (for Agency/Domain lookup)
   - Assumes CV.Agency(AgencyID) and CV.Domain(DomainID) already exist
   ======================================================================================= */

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

/* =======================================================================================
   1) CONTROLLED VOCABULARY CONTAINER
   ======================================================================================= */
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'rim')
    EXEC('CREATE SCHEMA rim');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'Master')
    EXEC('CREATE SCHEMA Master');
GO

IF OBJECT_ID(N'rim.RIM_CV', N'U') IS NOT NULL
    DROP TABLE rim.RIM_CV;
GO

CREATE TABLE rim.RIM_CV
(
    CV_ID                   INT IDENTITY(1,1) NOT NULL,
    AgencyID                INT NOT NULL,
    DomainID                INT NOT NULL,

    -- "Type" of codelist / value set
    CodeSystemName          NVARCHAR(150) NULL,
    CodeSystemOID           NVARCHAR(255) NULL,   -- max is rarely needed for OID/URI
    CodeSystem_Description  NVARCHAR(MAX) NULL,

    XPath1                  NVARCHAR(MAX) NULL,
    XPath2                  NVARCHAR(MAX) NULL,

    Support_Start_date      DATE NULL,
    RevisionNotes           NVARCHAR(MAX) NULL,

    IsCurrent               BIT NOT NULL CONSTRAINT DF_RIM_CV_IsCurrent DEFAULT (1),

    CONSTRAINT PK_RIM_CV PRIMARY KEY CLUSTERED (CV_ID ASC)
);
GO

ALTER TABLE rim.RIM_CV WITH CHECK
ADD CONSTRAINT FK_RIM_CV_Agency FOREIGN KEY (AgencyID)
REFERENCES CV.Agency (AgencyID);
GO

ALTER TABLE rim.RIM_CV WITH CHECK
ADD CONSTRAINT FK_RIM_CV_Domain FOREIGN KEY (DomainID)
REFERENCES CV.Domain (DomainID);
GO


/* =======================================================================================
   2) CONTROLLED VOCABULARY TERMS (ACTUAL VALUES)
   - All domain coded FKs point here (TermID)
   ======================================================================================= */
IF OBJECT_ID(N'rim.CV_Term', N'U') IS NOT NULL
    DROP TABLE rim.CV_Term;
GO

CREATE TABLE rim.CV_Term
(
    TermID                 INT IDENTITY(1,1) NOT NULL,
    CV_ID                  INT NOT NULL,

    IsActive               BIT NOT NULL CONSTRAINT DF_CV_Term_IsActive DEFAULT (1),
    Status                 NCHAR(10) NOT NULL CONSTRAINT DF_CV_Term_Status DEFAULT (N'Active'),

    TermCode               NVARCHAR(100) NULL,     -- keep bounded for indexing
    TermDescription        NVARCHAR(1000) NULL,    -- display label for reporting/UI

    Remarks                NVARCHAR(MAX) NULL,
    Additional_Information NVARCHAR(MAX) NULL,

    CONSTRAINT PK_CV_Term PRIMARY KEY CLUSTERED (TermID ASC),

    CONSTRAINT FK_CV_Term_RIM_CV
        FOREIGN KEY (CV_ID) REFERENCES rim.RIM_CV (CV_ID)
);
GO

-- Optional but strongly recommended uniqueness within a codelist
-- (adjust if your term codes are not unique)
CREATE UNIQUE INDEX UX_CV_Term_CV_TermCode
ON rim.CV_Term (CV_ID, TermCode)
WHERE TermCode IS NOT NULL;
GO

CREATE INDEX IX_CV_Term_CV
ON rim.CV_Term (CV_ID, IsActive)
INCLUDE (TermCode, TermDescription, Status);
GO


/* =======================================================================================
   3) ORGANISATION (SIMPLE / FLAT VERSIONED TABLE) - as provided
   ======================================================================================= */
IF OBJECT_ID(N'Master.Organisation_Version', N'U') IS NOT NULL
    DROP TABLE Master.Organisation_Version;
GO

CREATE TABLE Master.Organisation_Version
(
    Org_version_sk     BIGINT IDENTITY(1,1) NOT NULL,
    Org_sk             BIGINT NOT NULL,

    Org_name           NVARCHAR(2000) NOT NULL,
    Org_type           NVARCHAR(200) NULL,
    Org_internal_code  NVARCHAR(255) NULL,
    Status             NVARCHAR(50) NULL,

    HQ_Address_line1   NVARCHAR(2000) NULL,
    HQ_Address_line2   NVARCHAR(2000) NULL,
    HQ_Address_line3   NVARCHAR(2000) NULL,
    HQ_City            NVARCHAR(200) NULL,
    HQ_Country         NVARCHAR(100) NULL,
    HQ_postcode        NVARCHAR(50) NULL,

    valid_from         DATETIME2(0) NOT NULL,
    valid_to           DATETIME2(0) NOT NULL,
    is_current         BIT NOT NULL,
    last_updated_on    DATETIME2(0) NOT NULL,

    CONSTRAINT PK_Organisation_Version PRIMARY KEY CLUSTERED (Org_version_sk ASC)
);
GO

CREATE INDEX IX_OrgVersion_Current
ON Master.Organisation_Version (Org_sk, is_current)
INCLUDE (Org_name, Org_type, Status);
GO


/* =======================================================================================
   4) MEDICINAL PRODUCTS
   - coded fields: Combine_dose_form_TermID, Jurisdiction_TermID -> rim.CV_Term(TermID)
   - denorm fields: Combined_dose_form_denorm, Jurisdiction_denorm auto-maintained
   ======================================================================================= */
IF OBJECT_ID(N'rim.Medicinal_Products', N'U') IS NOT NULL
    DROP TABLE rim.Medicinal_Products;
GO

CREATE TABLE rim.Medicinal_Products
(
    Med_Prod_sk                    INT IDENTITY(1,1) NOT NULL,
    MPID                           VARCHAR(255) NOT NULL,
    Internal_MPID                  VARCHAR(255) NOT NULL,

    Current_flag                   BIT NOT NULL CONSTRAINT DF_MP_Current DEFAULT (1),

    Paediatric_use_indication_flag BIT NOT NULL CONSTRAINT DF_MP_Paed DEFAULT (0),
    Orphan_designation             BIT NOT NULL CONSTRAINT DF_MP_Orphan DEFAULT (0),
    combined_product_flag          BIT NOT NULL CONSTRAINT DF_MP_Combined DEFAULT (0),

    -- FK to rim.CV_Term (TermID)
    Combine_dose_form_TermID       INT NULL,
    Combined_dose_form_denorm      NVARCHAR(255) NULL,

    Additional_monitoring_flag     BIT NOT NULL CONSTRAINT DF_MP_AddMon DEFAULT (0),

    Validity_Start_Date            DATE NOT NULL CONSTRAINT DF_MP_ValidFrom DEFAULT (GETDATE()),
    Validity_End_Date              DATE NULL,

    -- FK to rim.CV_Term (TermID) - for MHRA-only you can populate with a single UK term
    Jurisdiction_TermID            INT NULL,
    Jurisdiction_denorm            NVARCHAR(255) NULL,

    CONSTRAINT PK_Med_Prod PRIMARY KEY CLUSTERED (Med_Prod_sk ASC)
);
GO

-- Uniqueness (adjust to your rules)
CREATE UNIQUE INDEX UX_MP_MPID_Current
ON rim.Medicinal_Products (MPID)
WHERE Current_flag = 1;
GO

ALTER TABLE rim.Medicinal_Products WITH CHECK
ADD CONSTRAINT FK_MP_CombineDoseForm_Term
FOREIGN KEY (Combine_dose_form_TermID) REFERENCES rim.CV_Term (TermID);
GO

ALTER TABLE rim.Medicinal_Products WITH CHECK
ADD CONSTRAINT FK_MP_Jurisdiction_Term
FOREIGN KEY (Jurisdiction_TermID) REFERENCES rim.CV_Term (TermID);
GO


/* =======================================================================================
   5) MEDICINAL PRODUCT NAMES (CHILD)
   - coded field: Name_type_TermID -> rim.CV_Term(TermID)
   - denorm field: Name_type_denorm auto-maintained
   ======================================================================================= */
IF OBJECT_ID(N'rim.Medicinal_Product_Names', N'U') IS NOT NULL
    DROP TABLE rim.Medicinal_Product_Names;
GO

CREATE TABLE rim.Medicinal_Product_Names
(
    Med_Prod_Name_sk               INT IDENTITY(1,1) NOT NULL,
    Med_Prod_sk                    INT NOT NULL,

    Country_Code                   CHAR(2) NULL,       -- UK only: 'GB' or 'UK' per your internal convention
    Language_Code                  VARCHAR(10) NULL,   -- e.g. 'en', 'en-GB'

    Full_Name                      VARCHAR(1024) NOT NULL,

    -- FK to rim.CV_Term (TermID)
    Name_type_TermID               INT NOT NULL,
    Name_type_denorm               NVARCHAR(255) NULL,

    Invented_Name_Part             VARCHAR(512) NULL,
    Scientific_Name_Part           VARCHAR(512) NULL,
    Strength_Part                  VARCHAR(255) NULL,
    Pharmaceutical_Dose_Form_Part  VARCHAR(255) NULL,
    Formulation_Part               VARCHAR(255) NULL,
    Intended_Use_Part              VARCHAR(255) NULL,
    Target_Population_Part         VARCHAR(255) NULL,

    Is_Preferred                   BIT NOT NULL CONSTRAINT DF_MPName_IsPreferred DEFAULT (0),
    Name_Source                    VARCHAR(50) NULL,

    Validity_Start_Date            DATE NOT NULL CONSTRAINT DF_MPName_ValidFrom DEFAULT (GETDATE()),
    Validity_End_Date              DATE NULL,

    CONSTRAINT PK_Medicinal_Product_Names
        PRIMARY KEY CLUSTERED (Med_Prod_Name_sk ASC),

    CONSTRAINT FK_MPNames_MedicinalProducts
        FOREIGN KEY (Med_Prod_sk) REFERENCES rim.Medicinal_Products (Med_Prod_sk),

    CONSTRAINT FK_MPNames_NameType_Term
        FOREIGN KEY (Name_type_TermID) REFERENCES rim.CV_Term (TermID),

    CONSTRAINT UQ_MPNames_Product_Context_Name_Period
        UNIQUE (Med_Prod_sk, Country_Code, Language_Code, Full_Name, Validity_Start_Date)
);
GO

CREATE INDEX IX_MPNames_Product_Preferred
ON rim.Medicinal_Product_Names (Med_Prod_sk, Is_Preferred)
INCLUDE (Full_Name, Country_Code, Language_Code, Name_type_denorm);
GO


/* =======================================================================================
   6) MARKETING AUTHORISATION (MHRA/UK PoC)
   - coded fields: procedure_type_TermID, authorisation_status_TermID -> rim.CV_Term(TermID)
   - denorm fields: Procedure_Type_denorm, Authorisation_Status_denorm auto-maintained
   ======================================================================================= */
IF OBJECT_ID(N'rim.MA_Marketing_Authorisation', N'U') IS NOT NULL
    DROP TABLE rim.MA_Marketing_Authorisation;
GO

CREATE TABLE rim.MA_Marketing_Authorisation
(
    MA_sk                           INT IDENTITY(1,1) NOT NULL,
    Authorisation_Number            VARCHAR(255) NOT NULL,

    -- keep simple: points to the current org version row, or an org master key – your call.
    -- For PoC, we leave it as a BIGINT that can reference Master.Organisation_Version.Org_version_sk if desired.
    Authorisation_holder_org_sk     BIGINT NULL,

    First_Authorisation_Date        DATE NOT NULL,

    -- FK to rim.CV_Term
    authorisation_status_TermID     INT NULL,
    Authorisation_Status_denorm     NVARCHAR(255) NULL,

    Authorisation_Status_Date       DATE NOT NULL,

    Validity_Start_Date             DATE NOT NULL,
    Validity_End_Date               DATE NOT NULL,

    Exclusivity_Start_Date          DATE NOT NULL,
    Exclusivity_End_Date            DATE NOT NULL,

    International_Birth_Date        DATE NOT NULL,

    -- FK to rim.CV_Term
    procedure_type_TermID           INT NULL,
    Procedure_Type_denorm           NVARCHAR(255) NULL,

    Procedure_Start_date            DATE NOT NULL,
    Procedure_End_date              DATE NOT NULL,

    Current_flag                    BIT NOT NULL CONSTRAINT DF_MA_Current DEFAULT (1),

    CONSTRAINT PK_MA_sk PRIMARY KEY CLUSTERED (MA_sk ASC)
);
GO

-- If you want an FK to organisation version (optional; comment out if not desired)
-- ALTER TABLE rim.MA_Marketing_Authorisation WITH CHECK
-- ADD CONSTRAINT FK_MA_OrgVersion
-- FOREIGN KEY (Authorisation_holder_org_sk) REFERENCES Master.Organisation_Version (Org_version_sk);
-- GO

ALTER TABLE rim.MA_Marketing_Authorisation WITH CHECK
ADD CONSTRAINT FK_MA_ProcedureType_Term
FOREIGN KEY (procedure_type_TermID) REFERENCES rim.CV_Term (TermID);
GO

ALTER TABLE rim.MA_Marketing_Authorisation WITH CHECK
ADD CONSTRAINT FK_MA_AuthorisationStatus_Term
FOREIGN KEY (authorisation_status_TermID) REFERENCES rim.CV_Term (TermID);
GO

CREATE UNIQUE INDEX UX_MA_AuthNumber_Current
ON rim.MA_Marketing_Authorisation (Authorisation_Number)
WHERE Current_flag = 1;
GO


/* =======================================================================================
   7) TRIGGERS: MAINTAIN DENORMALISED DISPLAY VALUES
   - Domain table triggers: when FK changes, populate *_denorm from rim.CV_Term.TermDescription
   - CV term trigger: when TermDescription changes, propagate to all dependent denorm columns
   ======================================================================================= */

--------------------------------------------------------------------------------------------
-- 7A) Domain trigger: rim.Medicinal_Products
--------------------------------------------------------------------------------------------
IF OBJECT_ID(N'rim.TR_MP_SetDenormFromTerm', N'TR') IS NOT NULL
    DROP TRIGGER rim.TR_MP_SetDenormFromTerm;
GO

CREATE TRIGGER rim.TR_MP_SetDenormFromTerm
ON rim.Medicinal_Products
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- Update denorms only for rows affected
    UPDATE mp
      SET Combined_dose_form_denorm = t1.TermDescription,
          Jurisdiction_denorm       = t2.TermDescription
    FROM rim.Medicinal_Products mp
    INNER JOIN inserted i
        ON i.Med_Prod_sk = mp.Med_Prod_sk
    LEFT JOIN rim.CV_Term t1
        ON t1.TermID = mp.Combine_dose_form_TermID
    LEFT JOIN rim.CV_Term t2
        ON t2.TermID = mp.Jurisdiction_TermID;
END;
GO

--------------------------------------------------------------------------------------------
-- 7B) Domain trigger: rim.Medicinal_Product_Names
--------------------------------------------------------------------------------------------
IF OBJECT_ID(N'rim.TR_MPNames_SetDenormFromTerm', N'TR') IS NOT NULL
    DROP TRIGGER rim.TR_MPNames_SetDenormFromTerm;
GO

CREATE TRIGGER rim.TR_MPNames_SetDenormFromTerm
ON rim.Medicinal_Product_Names
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE n
      SET Name_type_denorm = t.TermDescription
    FROM rim.Medicinal_Product_Names n
    INNER JOIN inserted i
        ON i.Med_Prod_Name_sk = n.Med_Prod_Name_sk
    LEFT JOIN rim.CV_Term t
        ON t.TermID = n.Name_type_TermID;
END;
GO

--------------------------------------------------------------------------------------------
-- 7C) Domain trigger: rim.MA_Marketing_Authorisation
--------------------------------------------------------------------------------------------
IF OBJECT_ID(N'rim.TR_MA_SetDenormFromTerm', N'TR') IS NOT NULL
    DROP TRIGGER rim.TR_MA_SetDenormFromTerm;
GO

CREATE TRIGGER rim.TR_MA_SetDenormFromTerm
ON rim.MA_Marketing_Authorisation
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE ma
      SET Procedure_Type_denorm       = pt.TermDescription,
          Authorisation_Status_denorm = st.TermDescription
    FROM rim.MA_Marketing_Authorisation ma
    INNER JOIN inserted i
        ON i.MA_sk = ma.MA_sk
    LEFT JOIN rim.CV_Term pt
        ON pt.TermID = ma.procedure_type_TermID
    LEFT JOIN rim.CV_Term st
        ON st.TermID = ma.authorisation_status_TermID;
END;
GO

--------------------------------------------------------------------------------------------
-- 7D) Term trigger: when TermDescription changes, propagate to denorm columns
--------------------------------------------------------------------------------------------
IF OBJECT_ID(N'rim.TR_CVTerm_PropagateDenorm', N'TR') IS NOT NULL
    DROP TRIGGER rim.TR_CVTerm_PropagateDenorm;
GO

CREATE TRIGGER rim.TR_CVTerm_PropagateDenorm
ON rim.CV_Term
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT UPDATE(TermDescription)
        RETURN;

    ;WITH Changed AS
    (
        SELECT i.TermID, i.TermDescription
        FROM inserted i
        INNER JOIN deleted d
            ON d.TermID = i.TermID
        WHERE ISNULL(i.TermDescription, N'') <> ISNULL(d.TermDescription, N'')
    )
    -- Medicinal_Products
    UPDATE mp
      SET Combined_dose_form_denorm = c.TermDescription
    FROM rim.Medicinal_Products mp
    INNER JOIN Changed c
      ON c.TermID = mp.Combine_dose_form_TermID;

    UPDATE mp
      SET Jurisdiction_denorm = c.TermDescription
    FROM rim.Medicinal_Products mp
    INNER JOIN Changed c
      ON c.TermID = mp.Jurisdiction_TermID;

    -- Medicinal_Product_Names
    UPDATE n
      SET Name_type_denorm = c.TermDescription
    FROM rim.Medicinal_Product_Names n
    INNER JOIN Changed c
      ON c.TermID = n.Name_type_TermID;

    -- Marketing Authorisation
    UPDATE ma
      SET Procedure_Type_denorm = c.TermDescription
    FROM rim.MA_Marketing_Authorisation ma
    INNER JOIN Changed c
      ON c.TermID = ma.procedure_type_TermID;

    UPDATE ma
      SET Authorisation_Status_denorm = c.TermDescription
    FROM rim.MA_Marketing_Authorisation ma
    INNER JOIN Changed c
      ON c.TermID = ma.authorisation_status_TermID;
END;
GO


/* =======================================================================================
   8) OPTIONAL: BACKFILL DENORMS ON EXISTING DATA (run once after loading data)
   ======================================================================================= */
-- EXEC sp_executesql N'
-- UPDATE mp
--   SET Combined_dose_form_denorm = t1.TermDescription,
--       Jurisdiction_denorm       = t2.TermDescription
-- FROM rim.Medicinal_Products mp
-- LEFT JOIN rim.CV_Term t1 ON t1.TermID = mp.Combine_dose_form_TermID
-- LEFT JOIN rim.CV_Term t2 ON t2.TermID = mp.Jurisdiction_TermID;
--
-- UPDATE n
--   SET Name_type_denorm = t.TermDescription
-- FROM rim.Medicinal_Product_Names n
-- LEFT JOIN rim.CV_Term t ON t.TermID = n.Name_type_TermID;
--
-- UPDATE ma
--   SET Procedure_Type_denorm       = pt.TermDescription,
--       Authorisation_Status_denorm = st.TermDescription
-- FROM rim.MA_Marketing_Authorisation ma
-- LEFT JOIN rim.CV_Term pt ON pt.TermID = ma.procedure_type_TermID
-- LEFT JOIN rim.CV_Term st ON st.TermID = ma.authorisation_status_TermID;
-- ';
GO

-- =========================================================
-- Table: RIM.MHRA_OrphanDesignation
-- Purpose: Load MHRA Orphan Register (current + expired) and
--          normalise designation numbers into 1 row each.
-- =========================================================
IF SCHEMA_ID('RIM') IS NULL
    EXEC('CREATE SCHEMA RIM');
GO

IF OBJECT_ID('RIM.MHRA_OrphanDesignation', 'U') IS  NULL


CREATE TABLE RIM.MHRA_OrphanDesignation
(
    orphan_id                 BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,

    -- Allows linking later by your own SMPC table key
    smpc_id                   BIGINT NULL,

    -- Source identification
    source_status             VARCHAR(20) NOT NULL,  -- 'current' | 'expired'
    source_file               NVARCHAR(260) NULL,
    source_rownum             INT NULL,

    -- MHRA columns (kept for traceability)
    product_name              NVARCHAR(300) NULL,
    active_substance          NVARCHAR(1000) NULL,
    orphan_condition          NVARCHAR(1000) NULL,
    od_indication             NVARCHAR(MAX) NULL,

    -- Normalised designation token (one per row)
    designation_number_raw    NVARCHAR(200) NOT NULL,

    -- Derived key you will use to map to SMPC
    authorisation_number      NVARCHAR(30) NULL,      -- e.g. 'PLGB 52115/0001'

    -- Optional: handy if you ever need it
    designation_suffix        NVARCHAR(20) NULL,      -- e.g. 'OD1', 'OD2'

    orphan_me_expiry_date     DATE NULL,
    designation_removed_date  DATE NULL,              -- present in expired file

    -- Audit
    loaded_utc                DATETIME2(0) NOT NULL CONSTRAINT DF_MHRA_OD_loaded_utc DEFAULT (SYSUTCDATETIME())
);
GO

-- Uniqueness: MHRA designation token + status is your natural key
CREATE UNIQUE INDEX UX_MHRA_OD_status_designation
ON RIM.MHRA_OrphanDesignation (source_status, designation_number_raw);

-- Fast mapping to SMPC
CREATE INDEX IX_MHRA_OD_authorisation
ON RIM.MHRA_OrphanDesignation (authorisation_number);

CREATE INDEX IX_MHRA_OD_smpc
ON RIM.MHRA_OrphanDesignation (smpc_id);
GO


/* =======================================================================================
   9) ADMINISTRABLE PRODUCT
   - An Administrable Product (PhPID) is the dose-form-specific view of a Medicinal Product.
   - One Medicinal Product may have one or more Administrable Products (e.g. tablet + oral solution).
   - coded fields: Dose_form_TermID, Unit_of_presentation_TermID -> rim.CV_Term(TermID)
   ======================================================================================= */
IF OBJECT_ID(N'rim.Administrable_Product', N'U') IS NOT NULL
    DROP TABLE rim.Administrable_Product;
GO

CREATE TABLE rim.Administrable_Product
(
    AdmProd_sk                      INT IDENTITY(1,1) NOT NULL,
    Med_Prod_sk                     INT NOT NULL,           -- parent Medicinal Product

    PhPID                           VARCHAR(255) NULL,      -- Pharmaceutical Product ID (IDMP)
    Internal_PhPID                  VARCHAR(255) NULL,

    -- Administrable dose form (e.g. "Tablet", "Oral solution")
    Dose_form_TermID                INT NULL,
    Dose_form_denorm                NVARCHAR(255) NULL,

    -- Unit of presentation (e.g. "Tablet", "Vial", "Ampoule")
    Unit_of_presentation_TermID     INT NULL,
    Unit_of_presentation_denorm     NVARCHAR(255) NULL,

    -- Release characteristics (e.g. "Modified-release", "Immediate-release")
    Release_characteristics_TermID  INT NULL,
    Release_characteristics_denorm  NVARCHAR(255) NULL,

    Current_flag                    BIT NOT NULL CONSTRAINT DF_AP_Current DEFAULT (1),
    Validity_Start_Date             DATE NOT NULL CONSTRAINT DF_AP_ValidFrom DEFAULT (GETDATE()),
    Validity_End_Date               DATE NULL,

    CONSTRAINT PK_AdmProd PRIMARY KEY CLUSTERED (AdmProd_sk ASC),

    CONSTRAINT FK_AP_MedicinalProduct
        FOREIGN KEY (Med_Prod_sk) REFERENCES rim.Medicinal_Products (Med_Prod_sk),

    CONSTRAINT FK_AP_DoseForm_Term
        FOREIGN KEY (Dose_form_TermID) REFERENCES rim.CV_Term (TermID),

    CONSTRAINT FK_AP_UnitOfPresentation_Term
        FOREIGN KEY (Unit_of_presentation_TermID) REFERENCES rim.CV_Term (TermID),

    CONSTRAINT FK_AP_ReleaseChar_Term
        FOREIGN KEY (Release_characteristics_TermID) REFERENCES rim.CV_Term (TermID)
);
GO

CREATE INDEX IX_AP_MedicinalProduct
ON rim.Administrable_Product (Med_Prod_sk, Current_flag)
INCLUDE (Dose_form_denorm, Unit_of_presentation_denorm);
GO

--------------------------------------------------------------------------------------------
-- Trigger 9A: maintain denorm columns on Administrable_Product
--------------------------------------------------------------------------------------------
IF OBJECT_ID(N'rim.TR_AP_SetDenormFromTerm', N'TR') IS NOT NULL
    DROP TRIGGER rim.TR_AP_SetDenormFromTerm;
GO

CREATE TRIGGER rim.TR_AP_SetDenormFromTerm
ON rim.Administrable_Product
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE ap
      SET Dose_form_denorm               = t1.TermDescription,
          Unit_of_presentation_denorm    = t2.TermDescription,
          Release_characteristics_denorm = t3.TermDescription
    FROM rim.Administrable_Product ap
    INNER JOIN inserted i
        ON i.AdmProd_sk = ap.AdmProd_sk
    LEFT JOIN rim.CV_Term t1 ON t1.TermID = ap.Dose_form_TermID
    LEFT JOIN rim.CV_Term t2 ON t2.TermID = ap.Unit_of_presentation_TermID
    LEFT JOIN rim.CV_Term t3 ON t3.TermID = ap.Release_characteristics_TermID;
END;
GO


/* =======================================================================================
   10) ROUTE OF ADMINISTRATION
   - Multiple routes may be associated with one Administrable Product (e.g. IV + IM).
   - coded field: Route_TermID -> rim.CV_Term(TermID)
   ======================================================================================= */
IF OBJECT_ID(N'rim.Route_of_Administration', N'U') IS NOT NULL
    DROP TABLE rim.Route_of_Administration;
GO

CREATE TABLE rim.Route_of_Administration
(
    RoA_sk          INT IDENTITY(1,1) NOT NULL,
    AdmProd_sk      INT NOT NULL,           -- parent Administrable Product

    -- Route (e.g. "Oral", "Intravenous", "Topical")
    Route_TermID    INT NOT NULL,
    Route_denorm    NVARCHAR(255) NULL,

    CONSTRAINT PK_RoA PRIMARY KEY CLUSTERED (RoA_sk ASC),

    CONSTRAINT FK_RoA_AdminProduct
        FOREIGN KEY (AdmProd_sk) REFERENCES rim.Administrable_Product (AdmProd_sk),

    CONSTRAINT FK_RoA_Route_Term
        FOREIGN KEY (Route_TermID) REFERENCES rim.CV_Term (TermID),

    CONSTRAINT UQ_RoA_Product_Route
        UNIQUE (AdmProd_sk, Route_TermID)   -- one row per product/route combination
);
GO

CREATE INDEX IX_RoA_AdminProduct
ON rim.Route_of_Administration (AdmProd_sk)
INCLUDE (Route_denorm);
GO

--------------------------------------------------------------------------------------------
-- Trigger 10A: maintain denorm columns on Route_of_Administration
--------------------------------------------------------------------------------------------
IF OBJECT_ID(N'rim.TR_RoA_SetDenormFromTerm', N'TR') IS NOT NULL
    DROP TRIGGER rim.TR_RoA_SetDenormFromTerm;
GO

CREATE TRIGGER rim.TR_RoA_SetDenormFromTerm
ON rim.Route_of_Administration
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE r
      SET Route_denorm = t.TermDescription
    FROM rim.Route_of_Administration r
    INNER JOIN inserted i ON i.RoA_sk = r.RoA_sk
    LEFT JOIN rim.CV_Term t ON t.TermID = r.Route_TermID;
END;
GO


/* =======================================================================================
   11) ADMINISTRABLE PRODUCT DEVICE
   - A device component integral to the administrable form (e.g. pre-filled syringe, inhaler).
   - coded field: Device_type_TermID -> rim.CV_Term(TermID)
   ======================================================================================= */
IF OBJECT_ID(N'rim.Administrable_Product_Device', N'U') IS NOT NULL
    DROP TABLE rim.Administrable_Product_Device;
GO

CREATE TABLE rim.Administrable_Product_Device
(
    Device_sk               INT IDENTITY(1,1) NOT NULL,
    AdmProd_sk              INT NOT NULL,

    -- Device type (e.g. "Pre-filled syringe", "Metered-dose inhaler")
    Device_type_TermID      INT NULL,
    Device_type_denorm      NVARCHAR(255) NULL,
    

    Device_description      NVARCHAR(500) NULL,     -- free-text supplement to coded type
    Quantity                DECIMAL(18,4) NULL,     -- number of device units per pack / dose

    CONSTRAINT PK_Device PRIMARY KEY CLUSTERED (Device_sk ASC),

    CONSTRAINT FK_Device_AdminProduct
        FOREIGN KEY (AdmProd_sk) REFERENCES rim.Administrable_Product (AdmProd_sk),

    CONSTRAINT FK_Device_DeviceType_Term
        FOREIGN KEY (Device_type_TermID) REFERENCES rim.CV_Term (TermID)
);
GO

CREATE INDEX IX_Device_AdminProduct
ON rim.Administrable_Product_Device (AdmProd_sk)
INCLUDE (Device_type_denorm);
GO

--------------------------------------------------------------------------------------------
-- Trigger 11A: maintain denorm columns on Administrable_Product_Device
--------------------------------------------------------------------------------------------
IF OBJECT_ID(N'rim.TR_Device_SetDenormFromTerm', N'TR') IS NOT NULL
    DROP TRIGGER rim.TR_Device_SetDenormFromTerm;
GO

CREATE TRIGGER rim.TR_Device_SetDenormFromTerm
ON rim.Administrable_Product_Device
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE d
      SET Device_type_denorm = t.TermDescription
    FROM rim.Administrable_Product_Device d
    INNER JOIN inserted i ON i.Device_sk = d.Device_sk
    LEFT JOIN rim.CV_Term t ON t.TermID = d.Device_type_TermID;
END;
GO


/* =======================================================================================
   12) INGREDIENTS
   - An Ingredient links a substance to an Administrable Product, with its role and quantity.
   - In IDMP, ingredients sit on the Pharmaceutical Product (Administrable Product) level.
   - coded fields: Ingredient_role_TermID, Qty_numerator_unit_TermID,
                   Qty_denominator_unit_TermID -> rim.CV_Term(TermID)
   ======================================================================================= */
IF OBJECT_ID(N'rim.Ingredient', N'U') IS NOT NULL
    DROP TABLE rim.Ingredient;
GO

CREATE TABLE rim.Ingredient
(
    Ingredient_sk                   INT IDENTITY(1,1) NOT NULL,
    AdmProd_sk                      INT NOT NULL,       -- parent Administrable Product

    -- Substance reference (FK to Staging.Substance)
    Substance_sk                    BIGINT NULL,           -- FK -> Staging.Substance(substance_sk)
    Substance_name                  NVARCHAR(500) NULL, -- denorm copy of preferred_name for reporting

    -- Role of this ingredient (e.g. "Active", "Excipient", "Adjuvant")
    Ingredient_role_TermID          INT NOT NULL,
    Ingredient_role_denorm          NVARCHAR(255) NULL,

    -- Quantity expressed as numerator / denominator (e.g. 500 mg per tablet)
    Qty_numerator_value             DECIMAL(18,6) NULL,
    Qty_numerator_unit_TermID       INT NULL,
    Qty_numerator_unit_denorm       NVARCHAR(255) NULL,

    Qty_denominator_value           DECIMAL(18,6) NULL,
    Qty_denominator_unit_TermID     INT NULL,
    Qty_denominator_unit_denorm     NVARCHAR(255) NULL,

    Is_reference_strength           BIT NOT NULL CONSTRAINT DF_Ing_RefStr DEFAULT (0),

    CONSTRAINT PK_Ingredient PRIMARY KEY CLUSTERED (Ingredient_sk ASC),

    CONSTRAINT FK_Ing_AdminProduct
        FOREIGN KEY (AdmProd_sk) REFERENCES rim.Administrable_Product (AdmProd_sk),

    CONSTRAINT FK_Ing_Role_Term
        FOREIGN KEY (Ingredient_role_TermID) REFERENCES rim.CV_Term (TermID),

    CONSTRAINT FK_Ing_NumeratorUnit_Term
        FOREIGN KEY (Qty_numerator_unit_TermID) REFERENCES rim.CV_Term (TermID),

    CONSTRAINT FK_Ing_DenominatorUnit_Term
        FOREIGN KEY (Qty_denominator_unit_TermID) REFERENCES rim.CV_Term (TermID),

    CONSTRAINT FK_Ing_Substance
        FOREIGN KEY (Substance_sk) REFERENCES Staging.Substance (substance_sk)
);
GO

CREATE INDEX IX_Ing_AdminProduct
ON rim.Ingredient (AdmProd_sk, Ingredient_role_TermID)
INCLUDE (Substance_name, Ingredient_role_denorm);
GO

CREATE INDEX IX_Ing_Substance
ON rim.Ingredient (Substance_sk)
INCLUDE (Substance_name);
GO

--------------------------------------------------------------------------------------------
-- Trigger 12A: maintain denorm columns on Ingredient
--------------------------------------------------------------------------------------------
IF OBJECT_ID(N'rim.TR_Ing_SetDenormFromTerm', N'TR') IS NOT NULL
    DROP TRIGGER rim.TR_Ing_SetDenormFromTerm;
GO

CREATE TRIGGER rim.TR_Ing_SetDenormFromTerm
ON rim.Ingredient
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE ing
      SET Ingredient_role_denorm      = t1.TermDescription,
          Qty_numerator_unit_denorm   = t2.TermDescription,
          Qty_denominator_unit_denorm = t3.TermDescription
    FROM rim.Ingredient ing
    INNER JOIN inserted i ON i.Ingredient_sk = ing.Ingredient_sk
    LEFT JOIN rim.CV_Term t1 ON t1.TermID = ing.Ingredient_role_TermID
    LEFT JOIN rim.CV_Term t2 ON t2.TermID = ing.Qty_numerator_unit_TermID
    LEFT JOIN rim.CV_Term t3 ON t3.TermID = ing.Qty_denominator_unit_TermID;
END;
GO


/* =======================================================================================
   13) INGREDIENT MANUFACTURER
   - Tracks which organisation manufactured (or is the origin of) a specific ingredient.
   - One ingredient may have multiple manufacturers (e.g. API supplier + secondary site).
   - coded field: Mfr_role_TermID -> rim.CV_Term(TermID)
   ======================================================================================= */
IF OBJECT_ID(N'rim.Ingredient_Manufacturer', N'U') IS NOT NULL
    DROP TABLE rim.Ingredient_Manufacturer;
GO

CREATE TABLE rim.Ingredient_Manufacturer
(
    IngMfr_sk           INT IDENTITY(1,1) NOT NULL,
    Ingredient_sk       INT NOT NULL,

    -- Reference to the Organisation master (use Org_sk for latest / Org_version_sk for point-in-time)
    Org_sk              BIGINT NOT NULL,

    -- Role of the organisation for this ingredient (e.g. "Manufacturer", "Origin", "Importer")
    Mfr_role_TermID     INT NULL,
    Mfr_role_denorm     NVARCHAR(255) NULL,

    Validity_Start_Date DATE NOT NULL CONSTRAINT DF_IngMfr_ValidFrom DEFAULT (GETDATE()),
    Validity_End_Date   DATE NULL,
    Is_current          BIT NOT NULL CONSTRAINT DF_IngMfr_Current DEFAULT (1),

    CONSTRAINT PK_IngMfr PRIMARY KEY CLUSTERED (IngMfr_sk ASC),

    CONSTRAINT FK_IngMfr_Ingredient
        FOREIGN KEY (Ingredient_sk) REFERENCES rim.Ingredient (Ingredient_sk),

    CONSTRAINT FK_IngMfr_MfrRole_Term
        FOREIGN KEY (Mfr_role_TermID) REFERENCES rim.CV_Term (TermID)

    -- Optional FK to Master.Organisation_Version (enable when org master is ready):
    -- CONSTRAINT FK_IngMfr_Org
    --     FOREIGN KEY (Org_sk) REFERENCES Master.Organisation_Version (Org_sk)
);
GO

CREATE INDEX IX_IngMfr_Ingredient
ON rim.Ingredient_Manufacturer (Ingredient_sk, Is_current)
INCLUDE (Org_sk, Mfr_role_denorm);
GO

CREATE INDEX IX_IngMfr_Org
ON rim.Ingredient_Manufacturer (Org_sk, Is_current);
GO

--------------------------------------------------------------------------------------------
-- Trigger 13A: maintain denorm columns on Ingredient_Manufacturer
--------------------------------------------------------------------------------------------
IF OBJECT_ID(N'rim.TR_IngMfr_SetDenormFromTerm', N'TR') IS NOT NULL
    DROP TRIGGER rim.TR_IngMfr_SetDenormFromTerm;
GO

CREATE TRIGGER rim.TR_IngMfr_SetDenormFromTerm
ON rim.Ingredient_Manufacturer
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE im
      SET Mfr_role_denorm = t.TermDescription
    FROM rim.Ingredient_Manufacturer im
    INNER JOIN inserted i ON i.IngMfr_sk = im.IngMfr_sk
    LEFT JOIN rim.CV_Term t ON t.TermID = im.Mfr_role_TermID;
END;
GO


/* =======================================================================================
   7D EXTENDED: propagate CV_Term description changes to the new tables
   (Replaces / extends the original TR_CVTerm_PropagateDenorm trigger)
   ======================================================================================= */
IF OBJECT_ID(N'rim.TR_CVTerm_PropagateDenorm', N'TR') IS NOT NULL
    DROP TRIGGER rim.TR_CVTerm_PropagateDenorm;
GO

CREATE TRIGGER rim.TR_CVTerm_PropagateDenorm
ON rim.CV_Term
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT UPDATE(TermDescription)
        RETURN;

    ;WITH Changed AS
    (
        SELECT i.TermID, i.TermDescription
        FROM inserted i
        INNER JOIN deleted d ON d.TermID = i.TermID
        WHERE ISNULL(i.TermDescription, N'') <> ISNULL(d.TermDescription, N'')
    )

    -- Medicinal_Products
    UPDATE mp SET Combined_dose_form_denorm = c.TermDescription
    FROM rim.Medicinal_Products mp INNER JOIN Changed c ON c.TermID = mp.Combine_dose_form_TermID;

    UPDATE mp SET Jurisdiction_denorm = c.TermDescription
    FROM rim.Medicinal_Products mp INNER JOIN Changed c ON c.TermID = mp.Jurisdiction_TermID;

    -- Medicinal_Product_Names
    UPDATE n SET Name_type_denorm = c.TermDescription
    FROM rim.Medicinal_Product_Names n INNER JOIN Changed c ON c.TermID = n.Name_type_TermID;

    -- Marketing_Authorisation
    UPDATE ma SET Procedure_Type_denorm = c.TermDescription
    FROM rim.MA_Marketing_Authorisation ma INNER JOIN Changed c ON c.TermID = ma.procedure_type_TermID;

    UPDATE ma SET Authorisation_Status_denorm = c.TermDescription
    FROM rim.MA_Marketing_Authorisation ma INNER JOIN Changed c ON c.TermID = ma.authorisation_status_TermID;

    -- Administrable_Product
    UPDATE ap SET Dose_form_denorm = c.TermDescription
    FROM rim.Administrable_Product ap INNER JOIN Changed c ON c.TermID = ap.Dose_form_TermID;

    UPDATE ap SET Unit_of_presentation_denorm = c.TermDescription
    FROM rim.Administrable_Product ap INNER JOIN Changed c ON c.TermID = ap.Unit_of_presentation_TermID;

    UPDATE ap SET Release_characteristics_denorm = c.TermDescription
    FROM rim.Administrable_Product ap INNER JOIN Changed c ON c.TermID = ap.Release_characteristics_TermID;

    -- Route_of_Administration
    UPDATE r SET Route_denorm = c.TermDescription
    FROM rim.Route_of_Administration r INNER JOIN Changed c ON c.TermID = r.Route_TermID;

    -- Administrable_Product_Device
    UPDATE d SET Device_type_denorm = c.TermDescription
    FROM rim.Administrable_Product_Device d INNER JOIN Changed c ON c.TermID = d.Device_type_TermID;

    -- Ingredient
    UPDATE ing SET Ingredient_role_denorm = c.TermDescription
    FROM rim.Ingredient ing INNER JOIN Changed c ON c.TermID = ing.Ingredient_role_TermID;

    UPDATE ing SET Qty_numerator_unit_denorm = c.TermDescription
    FROM rim.Ingredient ing INNER JOIN Changed c ON c.TermID = ing.Qty_numerator_unit_TermID;

    UPDATE ing SET Qty_denominator_unit_denorm = c.TermDescription
    FROM rim.Ingredient ing INNER JOIN Changed c ON c.TermID = ing.Qty_denominator_unit_TermID;

    -- Ingredient_Manufacturer
    UPDATE im SET Mfr_role_denorm = c.TermDescription
    FROM rim.Ingredient_Manufacturer im INNER JOIN Changed c ON c.TermID = im.Mfr_role_TermID;

END;
GO

-- =========================================================
-- Standalone SQL Script
-- Creates/updates: RIM.usp_upsert_mhra_orphan_designation
-- Assumes table exists: RIM.MHRA_OrphanDesignation
-- =========================================================

IF SCHEMA_ID('RIM') IS NULL
    EXEC('CREATE SCHEMA RIM');
GO

CREATE OR ALTER PROCEDURE RIM.usp_upsert_mhra_orphan_designation
(
    @source_status            VARCHAR(20),
    @source_file              NVARCHAR(260),
    @source_rownum            INT,
    @product_name             NVARCHAR(300),
    @active_substance         NVARCHAR(1000),
    @orphan_condition         NVARCHAR(1000),
    @od_indication            NVARCHAR(MAX),
    @designation_number_raw   NVARCHAR(200),
    @authorisation_number     NVARCHAR(30),
    @designation_suffix       NVARCHAR(20),
    @orphan_me_expiry_date    DATE,
    @designation_removed_date DATE
)
AS
BEGIN
    SET NOCOUNT ON;

    /*
      Upsert rule:
        Natural key = (source_status, designation_number_raw)
      This matches the unique index:
        UX_MHRA_OD_status_designation
    */

    MERGE RIM.MHRA_OrphanDesignation AS tgt
    USING (SELECT
        @source_status          AS source_status,
        @designation_number_raw AS designation_number_raw
    ) AS src
    ON  tgt.source_status = src.source_status
    AND tgt.designation_number_raw = src.designation_number_raw

    WHEN MATCHED THEN
      UPDATE SET
        tgt.source_file              = @source_file,
        tgt.source_rownum            = @source_rownum,
        tgt.product_name             = @product_name,
        tgt.active_substance         = @active_substance,
        tgt.orphan_condition         = @orphan_condition,
        tgt.od_indication            = @od_indication,
        tgt.authorisation_number     = @authorisation_number,
        tgt.designation_suffix       = @designation_suffix,
        tgt.orphan_me_expiry_date    = @orphan_me_expiry_date,
        tgt.designation_removed_date = @designation_removed_date,
        tgt.loaded_utc               = SYSUTCDATETIME()

    WHEN NOT MATCHED THEN
      INSERT
      (
        source_status,
        source_file,
        source_rownum,
        product_name,
        active_substance,
        orphan_condition,
        od_indication,
        designation_number_raw,
        authorisation_number,
        designation_suffix,
        orphan_me_expiry_date,
        designation_removed_date
      )
      VALUES
      (
        @source_status,
        @source_file,
        @source_rownum,
        @product_name,
        @active_substance,
        @orphan_condition,
        @od_indication,
        @designation_number_raw,
        @authorisation_number,
        @designation_suffix,
        @orphan_me_expiry_date,
        @designation_removed_date
      );

END;
GO

