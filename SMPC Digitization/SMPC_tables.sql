/****** Object:  Table [Staging].[SMPC]    Script Date: 08/02/2026 14:20:23 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [Staging].[SMPC](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[country] [varchar](2) NOT NULL,
	[S1_Name_of_Medicinal_product] [varchar](max) NULL,
	[S2_Composition] [varchar](max) NULL,
	[S3_pharmaceutical_form] [nvarchar](max) NULL,
	[S_4_1_therapeutic_indications] [nvarchar](max) NULL,
	[S_4_2_posology_administration] [nvarchar](max) NULL,
	[S_4_3_contraindications] [nvarchar](max) NULL,
	[S_4_4_warnings_precautions] [nvarchar](max) NULL,
	[S_4_5_interactions] [nvarchar](max) NULL,
	[S_4_6_pregnancy_lactation] [nvarchar](max) NULL,
	[S_4_7_driving_machines] [nvarchar](max) NULL,
	[S_4_8_undesirable_effects] [nvarchar](max) NULL,
	[S_4_9_overdose] [nvarchar](max) NULL,
	[S_5_1_pharmacodynamics] [nvarchar](max) NULL,
	[S_5_2_pharmacokinetics] [nvarchar](max) NULL,
	[S_5_3_preclinical_data] [nvarchar](max) NULL,
	[S_6_1_excipients] [nvarchar](max) NULL,
	[S_6_2_incompatibilities] [nvarchar](max) NULL,
	[S_6_3_shelf_life] [nvarchar](max) NULL,
	[S_6_4_storage] [nvarchar](max) NULL,
	[S_6_5_container_description] [nvarchar](max) NULL,
	[S_6_6_handling_disposal] [nvarchar](max) NULL,
	[S_7_marketing_authorisation_holder] [nvarchar](max) NULL,
	[s_8_authorisation_number] [nvarchar](50) NULL,
	[S_9_authorisation_date] [date] NULL,
	[S_10_revision_date] [date] NULL,
	[last_updated] [date] NULL,
	[Source_file_name] [nvarchar](50) NULL,
	[last_updated_by] [nvarchar](50) NULL,
	[S2_Composition_cleaned] [nvarchar](max) NULL,
PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO

ALTER TABLE [Staging].[SMPC] ADD  DEFAULT ('System') FOR [last_updated_by]
GO


/****** Object:  Table [Staging].[PL_SPC_Indications]    Script Date: 08/02/2026 14:20:47 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [Staging].[PL_SPC_Indications](
	[PL_number] [varchar](100) NULL,
	[PT_Code] [varchar](100) NULL,
	[Present_in_SPC] [varchar](10) NULL
) ON [PRIMARY]
GO

/****** Object:  Table [Staging].[PL_SPC_Adverse_reaction]    Script Date: 08/02/2026 14:21:05 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [Staging].[PL_SPC_Adverse_reaction](
	[PL_number] [varchar](100) NULL,
	[PT_Code] [varchar](100) NULL,
	[Present_in_SPC] [varchar](10) NULL
) ON [PRIMARY]
GO

/****** Object:  Table [Staging].[SMPC_Meta_data]    Script Date: 08/02/2026 18:12:52 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [Staging].[SMPC_Meta_data](
	[Meta_data_id] [int] IDENTITY(1,1) NOT NULL,
	[SMPC_ID] [int] NOT NULL,
	[Agency_id] [int] NOT NULL,
	[Search_Score] [float] NULL,
	[Rev_Label] [nvarchar](50) NULL,
	[Highlights_Content_Text] [nvarchar](max) NULL,
	[Highlights_Content_JSON] [nvarchar](max) NULL,
	[Metadata_Storage_Path] [nvarchar](2048) NULL,
	[Metadata_Storage_Name] [nvarchar](512) NULL,
	[Metadata_Storage_Size] [bigint] NULL,
	[Product_Name] [nvarchar](512) NULL,
	[Created_UTC] [datetime2](0) NULL,
	[Release_State] [nvarchar](10) NULL,
	[Keywords] [nvarchar](max) NULL,
	[Title] [nvarchar](512) NULL,
	[Territory] [nvarchar](50) NULL,
	[File_Name] [nvarchar](200) NULL,
	[Doc_Type] [nvarchar](50) NULL,
	[PL_Number_JSON] [nvarchar](max) NULL,
	[Suggestions_JSON] [nvarchar](max) NULL,
	[Substance_Name_JSON] [nvarchar](max) NULL,
	[Facets_JSON] [nvarchar](max) NULL,
	[Raw_Item_JSON] [nvarchar](max) NULL,
	[Loaded_UTC] [datetime2](0) NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[Meta_data_id] ASC
)WITH (STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO

ALTER TABLE [Staging].[SMPC_Meta_data] ADD  CONSTRAINT [DF_SMPC_Meta_data_Loaded_UTC]  DEFAULT (sysutcdatetime()) FOR [Loaded_UTC]
GO

ALTER TABLE [Staging].[SMPC_Meta_data]  WITH CHECK ADD  CONSTRAINT [FK_SMPC_Meta_data_Agency] FOREIGN KEY([Agency_id])
REFERENCES [CV].[Agency] ([AgencyID])
GO

ALTER TABLE [Staging].[SMPC_Meta_data] CHECK CONSTRAINT [FK_SMPC_Meta_data_Agency]
GO

ALTER TABLE [Staging].[SMPC_Meta_data]  WITH CHECK ADD  CONSTRAINT [FK_SMPC_Meta_data_SMPC] FOREIGN KEY([SMPC_ID])
REFERENCES [Staging].[SMPC] ([id])
GO

ALTER TABLE [Staging].[SMPC_Meta_data] CHECK CONSTRAINT [FK_SMPC_Meta_data_SMPC]
GO


CREATE TABLE [rim].[MHRA_OrphanDesignation](
	[orphan_id] [bigint] IDENTITY(1,1) NOT NULL,
	[smpc_id] [bigint] NULL,
	[source_status] [varchar](20) NOT NULL,
	[source_file] [nvarchar](260) NULL,
	[source_rownum] [int] NULL,
	[product_name] [nvarchar](300) NULL,
	[active_substance] [nvarchar](1000) NULL,
	[orphan_condition] [nvarchar](1000) NULL,
	[od_indication] [nvarchar](max) NULL,
	[designation_number_raw] [nvarchar](200) NOT NULL,
	[authorisation_number] [nvarchar](30) NULL,
	[designation_suffix] [nvarchar](20) NULL,
	[orphan_me_expiry_date] [date] NULL,
	[designation_removed_date] [date] NULL,
	[loaded_utc] [datetime2](0) NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[orphan_id] ASC
)WITH (STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO

ALTER TABLE [rim].[MHRA_OrphanDesignation] ADD  CONSTRAINT [DF_MHRA_OD_loaded_utc]  DEFAULT (sysutcdatetime()) FOR [loaded_utc]
GO


CREATE TABLE [Staging].[Substance](
	[substance_sk] [bigint] IDENTITY(1,1) NOT NULL,
	[sms_id] [varchar](50) NOT NULL,
	[ev_code] [varchar](50) NULL,
	[preferred_name] [nvarchar](2000) NOT NULL,
	[substance_domain] [nvarchar](100) NULL,
	[status] [nvarchar](50) NULL,
	[substance_type] [nvarchar](200) NULL,
	[molecular_formula] [nvarchar](200) NULL,
	[molecular_weight] [nvarchar](50) NULL,
	[inchikey] [nvarchar](200) NULL,
	[comment] [nvarchar](2000) NULL,
	[created_date_raw] [nvarchar](50) NULL,
	[last_updated_raw] [nvarchar](50) NULL,
	[svg_flag] [nvarchar](50) NULL,
	[unii] [nvarchar](100) NULL,
	[inn_number] [nvarchar](100) NULL,
	[ec_list_number] [nvarchar](100) NULL,
	[parent_substance] [nvarchar](2000) NULL,
	[valid_from] [datetime2](0) NOT NULL,
	[valid_to] [datetime2](0) NOT NULL,
	[is_current] [bit] NOT NULL,
	[record_hash] [varbinary](32) NOT NULL,
	[load_id_created] [bigint] NOT NULL,
	[load_id_closed] [bigint] NULL,
	[created_at] [datetime2](0) NOT NULL,
	[closed_at] [datetime2](0) NULL,
	[Substance_Source] [nvarchar](100) NULL,
 CONSTRAINT [PK_Substance] PRIMARY KEY CLUSTERED 
(
	[substance_sk] ASC
)WITH (STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [Staging].[Substance] ADD  DEFAULT (sysdatetime()) FOR [created_at]
GO

ALTER TABLE [Staging].[Substance] ADD  DEFAULT ('EMA Substance list') FOR [Substance_Source]
GO




CREATE TABLE [Staging].[Substance_Name](
	[substance_name_sk] [bigint] IDENTITY(1,1) NOT NULL,
	[sms_id] [varchar](50) NOT NULL,
	[ev_code] [varchar](50) NULL,
	[name_text] [nvarchar](2000) NOT NULL,
	[language] [nvarchar](50) NULL,
	[name_source] [nvarchar](200) NULL,
	[name_key] [varbinary](32) NOT NULL,
	[valid_from] [datetime2](0) NOT NULL,
	[valid_to] [datetime2](0) NOT NULL,
	[is_current] [bit] NOT NULL,
	[record_hash] [varbinary](32) NOT NULL,
	[load_id_created] [bigint] NOT NULL,
	[load_id_closed] [bigint] NULL,
	[created_at] [datetime2](0) NOT NULL,
	[closed_at] [datetime2](0) NULL,
	[Substance_Source] [nvarchar](100) NULL,
 CONSTRAINT [PK_Substance_Name] PRIMARY KEY CLUSTERED 
(
	[substance_name_sk] ASC
)WITH (STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [Staging].[Substance_Name] ADD  DEFAULT (sysdatetime()) FOR [created_at]
GO

ALTER TABLE [Staging].[Substance_Name] ADD  DEFAULT ('EMA Substance list') FOR [Substance_Source]
GO


CREATE TABLE [Staging].[SMPC_Active_Substance](
	[SMPC_id] [int] NOT NULL,
	[Substance_sk] [int] NULL,
	[Substance_role] [varchar](250) NULL,
	[current_flag] [bit] NOT NULL,
	[Synonym_id] [int] NULL,
	[confidence_substance_match] [decimal](5, 4) NOT NULL,
	[rationale_substance_match] [nvarchar](2000) NULL,
	[confidence_synonym_match] [decimal](5, 4) NULL,
	[rationale_synonym_match] [nvarchar](2000) NULL,
	[model_used] [varchar](100) NOT NULL
) ON [PRIMARY]
GO

ALTER TABLE [Staging].[SMPC_Active_Substance] ADD  DEFAULT ((1)) FOR [current_flag]
GO

ALTER TABLE [Staging].[SMPC_Active_Substance] ADD  CONSTRAINT [DF_SMPC_Active_Substance_conf_substance]  DEFAULT ((1.0000)) FOR [confidence_substance_match]
GO

ALTER TABLE [Staging].[SMPC_Active_Substance] ADD  CONSTRAINT [DF_SMPC_Active_Substance_model]  DEFAULT ('unknown') FOR [model_used]
GO
