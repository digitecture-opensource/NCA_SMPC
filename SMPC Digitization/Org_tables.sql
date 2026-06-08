
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'Staging') EXEC('CREATE SCHEMA Staging');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'Master')  EXEC('CREATE SCHEMA Master');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'History') EXEC('CREATE SCHEMA History'); -- optional (kept for compatibility)
GO


IF OBJECT_ID('Master.Organisation', 'U') IS NULL
BEGIN
    CREATE TABLE Master.Organisation
    (
        Org_sk            BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Master_Organisation PRIMARY KEY,
        Org_internal_code NVARCHAR(200) NOT NULL,
        Created_on        DATETIME2(0) NOT NULL CONSTRAINT DF_Organisation_CreatedOn DEFAULT (SYSUTCDATETIME())
    );

    CREATE UNIQUE INDEX UX_Organisation_OrgInternalCode
    ON Master.Organisation(Org_internal_code);
END
GO

IF OBJECT_ID('Master.Organisation_Version', 'U') IS NULL
BEGIN
    CREATE TABLE Master.Organisation_Version
    (
        Org_version_sk  BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Organisation_Version PRIMARY KEY,
        Org_sk          BIGINT NOT NULL,

        Org_name        NVARCHAR(2000) NOT NULL,
        Org_type        NVARCHAR(max) NULL,
        [Status]        NVARCHAR(50) NULL,

        valid_from      DATETIME2(0) NOT NULL CONSTRAINT DF_OrgVer_ValidFrom DEFAULT (SYSUTCDATETIME()),
        valid_to        DATETIME2(0) NOT NULL CONSTRAINT DF_OrgVer_ValidTo DEFAULT (CONVERT(DATETIME2(0),'9999-12-31 00:00:00')),
        is_current      BIT NOT NULL CONSTRAINT DF_OrgVer_IsCurrent DEFAULT (1),

        last_updated_on DATETIME2(0) NOT NULL CONSTRAINT DF_OrgVer_LastUpd DEFAULT (SYSUTCDATETIME()),

        CONSTRAINT FK_OrgVer_Org FOREIGN KEY (Org_sk) REFERENCES Master.Organisation(Org_sk),
        CONSTRAINT CK_OrgVer_ValidRange CHECK (valid_from < valid_to)
    );

    -- Enforce only one current version per Org
    CREATE UNIQUE INDEX UX_OrgVer_Current
    ON Master.Organisation_Version(Org_sk)
    WHERE is_current = 1;

    CREATE INDEX IX_OrgVer_Org_Validity
    ON Master.Organisation_Version(Org_sk, is_current, valid_to);
END
GO

/* Convenience view: current organisation attributes */
IF OBJECT_ID('Master.vw_Organisation_Current', 'V') IS NULL
EXEC('
CREATE VIEW Master.vw_Organisation_Current AS
SELECT
    o.Org_sk,
    o.Org_internal_code,
    v.Org_version_sk,
    v.Org_name,
    v.Org_type,
    v.Status,
    v.valid_from,
    v.valid_to,
    v.last_updated_on
FROM Master.Organisation o
JOIN Master.Organisation_Version v
  ON v.Org_sk = o.Org_sk
 AND v.is_current = 1;
');
GO


/* =========================================
   4) MASTER.Org_address (ENTITY) + VERSION
========================================= */

IF OBJECT_ID('Master.Org_address', 'U') IS NULL
BEGIN
    CREATE TABLE Master.Org_address
    (
        Org_address_sk BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_OrgAddress PRIMARY KEY,
        Org_sk         BIGINT NOT NULL,
        Created_on     DATETIME2(0) NOT NULL CONSTRAINT DF_OrgAddr_Created DEFAULT (SYSUTCDATETIME()),

        CONSTRAINT FK_OrgAddr_Org FOREIGN KEY (Org_sk) REFERENCES Master.Organisation(Org_sk)
    );

    CREATE INDEX IX_OrgAddr_Org ON Master.Org_address(Org_sk);
END
GO

IF OBJECT_ID('Master.Org_address_Version', 'U') IS NULL
BEGIN
    CREATE TABLE Master.Org_address_Version
    (
        Org_address_version_sk BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_OrgAddress_Version PRIMARY KEY,
        Org_address_sk         BIGINT NOT NULL,

        HQ_Flag                BIT NOT NULL CONSTRAINT DF_OrgAddrV_HQ DEFAULT (0),

        line1     NVARCHAR(2000) NULL,
        line2     NVARCHAR(2000) NULL,
        line3     NVARCHAR(2000) NULL,
        
        line4     NVARCHAR(2000) NULL,
        address_po_box NVARCHAR(200) NULL,
        City      NVARCHAR(200)  NULL,
        Country   NVARCHAR(100)  NULL,
        postcode  NVARCHAR(50)   NULL,
        EMA_Location_link NVARCHAR(4000) NULL, -- optional link to EMA location page
        GPS_Coodinates NVARCHAR(500) NULL, -- optional free-text GPS coordinates

        Master_address_ref_sk  BIGINT NULL,

        valid_from DATETIME2(0) NOT NULL CONSTRAINT DF_OrgAddrV_ValidFrom DEFAULT (SYSUTCDATETIME()),
        valid_to   DATETIME2(0) NOT NULL CONSTRAINT DF_OrgAddrV_ValidTo DEFAULT (CONVERT(DATETIME2(0),'9999-12-31 00:00:00')),
        is_current BIT NOT NULL CONSTRAINT DF_OrgAddrV_IsCurrent DEFAULT (1),

        last_updated_on DATETIME2(0) NOT NULL CONSTRAINT DF_OrgAddrV_LastUpd DEFAULT (SYSUTCDATETIME()),

        CONSTRAINT FK_OrgAddrV_OrgAddr FOREIGN KEY (Org_address_sk) REFERENCES Master.Org_address(Org_address_sk),
         CONSTRAINT CK_OrgAddrV_ValidRange CHECK (valid_from < valid_to)
    );

    CREATE UNIQUE INDEX UX_OrgAddrV_Current
    ON Master.Org_address_Version(Org_address_sk)
    WHERE is_current = 1;

    CREATE INDEX IX_OrgAddrV_MAR ON Master.Org_address_Version(Master_address_ref_sk);
END
GO


/****** Object:  Table [Master].[Org_external_codes]    Script Date: 15/02/2026 21:01:14 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [Master].[Org_external_codes](
	[Code_sk] [bigint] IDENTITY(1,1) NOT NULL,
	[Org_sk] [bigint] NOT NULL,
	[Code_status] [nvarchar](50) NULL,
	[Source] [nvarchar](100) NOT NULL,
	[External_code] [nvarchar](4000) NULL,
	[Created_on] [datetime2](0) NOT NULL,
	[last_validated_on] [datetime2](0) NULL,
	[valid_start] [datetime2](0) NULL,
	[valid_end] [datetime2](0) NULL,
 CONSTRAINT [PK_Org_external_codes] PRIMARY KEY CLUSTERED 
(
	[Code_sk] ASC
)WITH (STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [Master].[Org_external_codes] ADD  CONSTRAINT [DF_OrgExt_Created]  DEFAULT (sysutcdatetime()) FOR [Created_on]
GO

ALTER TABLE [Master].[Org_external_codes]  WITH CHECK ADD  CONSTRAINT [FK_OrgExt_Org] FOREIGN KEY([Org_sk])
REFERENCES [Master].[Organisation] ([Org_sk])
GO

ALTER TABLE [Master].[Org_external_codes] CHECK CONSTRAINT [FK_OrgExt_Org]
GO





IF OBJECT_ID('Master.vw_OrgAddress_Current', 'V') IS NULL
EXEC('
CREATE VIEW Master.vw_OrgAddress_Current AS
SELECT
    a.Org_address_sk,
    a.Org_sk,
    v.Org_address_version_sk,
    v.HQ_Flag,
    v.line1, v.line2, v.line3, v.City, v.Country, v.postcode,
    v.Master_address_ref_sk,
    v.valid_from, v.valid_to, v.last_updated_on
FROM Master.Org_address a
JOIN Master.Org_address_Version v
  ON v.Org_address_sk = a.Org_address_sk
 AND v.is_current = 1;
');
GO



SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

/* ===========================
   Helper: constant max date
=========================== */
DECLARE @SCD_MAX_TO DATETIME2(0) = CONVERT(DATETIME2(0),'9999-12-31 00:00:00');
GO

/* =====================================================================================
   1) Organisation SCD2 Upsert
   Natural key: Org_internal_code
===================================================================================== */
CREATE OR ALTER PROCEDURE Master.usp_Organisation_SCD2_Upsert
    @Org_internal_code NVARCHAR(200),
    @Org_name          NVARCHAR(2000),
    @Org_type          NVARCHAR(200) = NULL,
    @Status            NVARCHAR(50) = NULL,
    @as_of             DATETIME2(0) = NULL,
    @Org_sk            BIGINT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @as_of IS NULL SET @as_of = SYSUTCDATETIME();

    BEGIN TRAN;

    -- Entity
    SELECT @Org_sk = Org_sk
    FROM Master.Organisation WITH (UPDLOCK, HOLDLOCK)
    WHERE Org_internal_code = @Org_internal_code;

    IF @Org_sk IS NULL
    BEGIN
        INSERT INTO Master.Organisation (Org_internal_code)
        VALUES (@Org_internal_code);

        SET @Org_sk = SCOPE_IDENTITY();
    END

    -- Current version (if any)
    DECLARE
        @cur_name   NVARCHAR(2000),
        @cur_type   NVARCHAR(200),
        @cur_status NVARCHAR(50),
        @cur_ver_sk BIGINT;

    SELECT TOP (1)
        @cur_ver_sk = Org_version_sk,
        @cur_name   = Org_name,
        @cur_type   = Org_type,
        @cur_status = [Status]
    FROM Master.Organisation_Version WITH (UPDLOCK, HOLDLOCK)
    WHERE Org_sk = @Org_sk AND is_current = 1;

    IF @cur_ver_sk IS NULL
    BEGIN
        INSERT INTO Master.Organisation_Version
        (Org_sk, Org_name, Org_type, [Status], valid_from, valid_to, is_current)
        VALUES
        (@Org_sk, @Org_name, @Org_type, @Status, @as_of, CONVERT(DATETIME2(0),'9999-12-31 00:00:00'), 1);

        COMMIT;
        RETURN;
    END

    -- If changed, close + insert
    IF (ISNULL(@cur_name,'') <> ISNULL(@Org_name,''))
       OR (ISNULL(@cur_type,'') <> ISNULL(@Org_type,''))
       OR (ISNULL(@cur_status,'') <> ISNULL(@Status,''))
    BEGIN
        UPDATE Master.Organisation_Version
        SET is_current = 0,
            valid_to   = @as_of,
            last_updated_on = SYSUTCDATETIME()
        WHERE Org_version_sk = @cur_ver_sk;

        INSERT INTO Master.Organisation_Version
        (Org_sk, Org_name, Org_type, [Status], valid_from, valid_to, is_current)
        VALUES
        (@Org_sk, @Org_name, @Org_type, @Status, @as_of, CONVERT(DATETIME2(0),'9999-12-31 00:00:00'), 1);
    END

    COMMIT;
END
GO

/* =====================================================================================
   3) Org Address SCD2 Upsert
   - If @Org_address_sk is NULL: create new address entity for Org_sk
   - Version includes HQ_Flag + address lines + optional Master_address_ref_sk
===================================================================================== */
CREATE OR ALTER PROCEDURE Master.usp_OrgAddress_SCD2_Upsert
    @Org_address_sk BIGINT = NULL,      -- optional: create new entity if NULL
    @Org_sk         BIGINT,
    @HQ_Flag        BIT = 0,
    @line1          NVARCHAR(2000) = NULL,
    @line2          NVARCHAR(2000) = NULL,
    @line3          NVARCHAR(2000) = NULL,
    @City           NVARCHAR(200)  = NULL,
    @Country        NVARCHAR(100)  = NULL,
    @postcode       NVARCHAR(50)   = NULL,
    @Master_address_ref_sk BIGINT  = NULL,
    @as_of          DATETIME2(0)   = NULL,
    @out_Org_address_sk BIGINT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @as_of IS NULL SET @as_of = SYSUTCDATETIME();

    BEGIN TRAN;

    -- Entity existence
    IF @Org_address_sk IS NULL
    BEGIN
        INSERT INTO Master.Org_address (Org_sk) VALUES (@Org_sk);
        SET @Org_address_sk = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM Master.Org_address WITH (UPDLOCK, HOLDLOCK)
                       WHERE Org_address_sk = @Org_address_sk)
        BEGIN
            INSERT INTO Master.Org_address (Org_address_sk, Org_sk, Created_on)
            VALUES (@Org_address_sk, @Org_sk, SYSUTCDATETIME());
        END
    END

    SET @out_Org_address_sk = @Org_address_sk;

    DECLARE
        @cur_ver_sk BIGINT,
        @cur_hq BIT,
        @cur_line1 NVARCHAR(2000),
        @cur_line2 NVARCHAR(2000),
        @cur_line3 NVARCHAR(2000),
        @cur_city NVARCHAR(200),
        @cur_country NVARCHAR(100),
        @cur_postcode NVARCHAR(50),
        @cur_mar BIGINT;

    SELECT TOP (1)
        @cur_ver_sk = Org_address_version_sk,
        @cur_hq = HQ_Flag,
        @cur_line1 = line1,
        @cur_line2 = line2,
        @cur_line3 = line3,
        @cur_city = City,
        @cur_country = Country,
        @cur_postcode = postcode,
        @cur_mar = Master_address_ref_sk
    FROM Master.Org_address_Version WITH (UPDLOCK, HOLDLOCK)
    WHERE Org_address_sk = @Org_address_sk AND is_current = 1;

    IF @cur_ver_sk IS NULL
    BEGIN
        INSERT INTO Master.Org_address_Version
        (Org_address_sk, HQ_Flag, line1, line2, line3, City, Country, postcode, Master_address_ref_sk,
         valid_from, valid_to, is_current)
        VALUES
        (@Org_address_sk, @HQ_Flag, @line1, @line2, @line3, @City, @Country, @postcode, @Master_address_ref_sk,
         @as_of, CONVERT(DATETIME2(0),'9999-12-31 00:00:00'), 1);

        COMMIT;
        RETURN;
    END

    IF (ISNULL(@cur_hq,0) <> ISNULL(@HQ_Flag,0))
       OR (ISNULL(@cur_line1,'') <> ISNULL(@line1,''))
       OR (ISNULL(@cur_line2,'') <> ISNULL(@line2,''))
       OR (ISNULL(@cur_line3,'') <> ISNULL(@line3,''))
       OR (ISNULL(@cur_city,'')  <> ISNULL(@City,''))
       OR (ISNULL(@cur_country,'') <> ISNULL(@Country,''))
       OR (ISNULL(@cur_postcode,'') <> ISNULL(@postcode,''))
       OR (ISNULL(@cur_mar,0) <> ISNULL(@Master_address_ref_sk,0))
    BEGIN
        UPDATE Master.Org_address_Version
        SET is_current = 0,
            valid_to = @as_of,
            last_updated_on = SYSUTCDATETIME()
        WHERE Org_address_version_sk = @cur_ver_sk;

        INSERT INTO Master.Org_address_Version
        (Org_address_sk, HQ_Flag, line1, line2, line3, City, Country, postcode, Master_address_ref_sk,
         valid_from, valid_to, is_current)
        VALUES
        (@Org_address_sk, @HQ_Flag, @line1, @line2, @line3, @City, @Country, @postcode, @Master_address_ref_sk,
         @as_of, CONVERT(DATETIME2(0),'9999-12-31 00:00:00'), 1);
    END

    COMMIT;
END
GO
