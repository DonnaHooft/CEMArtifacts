# CEM Artifacts Review - 3D Slicer Extension

A 3D Slicer extension for reviewing and annotating artifacts in Contrast-Enhanced Mammography (CEM) images.

## Overview

This extension enables systematic review of artifact presence in paired low-energy (LE/DM) and recombined (REC/CM) CEM images. It provides a guided workflow for:
- Identifying artifact presence
- Classifying artifact types
- Segmenting artifact regions
- Tracking annotation progress

## Features

- **Side-by-side image viewing** - Compare LE and Recombined images simultaneously
- **Artifact classification** - 8 predefined artifact types plus "Other"
- **Guided segmentation workflow** - Step-by-step interface for segmenting selected artifacts
- **Progress tracking** - Resume annotation sessions from where you left off
- **Review mode** - Review and edit previously completed annotations
- **Automatic mask saving** - Exports segmentations as .npy arrays and individual PNG files

## Requirements

- **3D Slicer version**: 5.6.2 or earlier (automatic artifact naming requires ≤5.6.2)
- **Python packages**: pandas, numpy, SimpleITK, Pillow (auto-installed on first run)

## Installation

1. Download the extension files
2. In 3D Slicer, go to: `Edit` → `Application Settings` → `Modules` → `Additional module paths`
3. Add the directory containing `CEMArtifacts.py`
4. Restart Slicer
5. Find "CEM Artifacts review" in the module list (under "Examples" category)

## Image Naming Convention

Images must follow this naming pattern:
```
P{patient}_{L|R}_{DM|CM}_{CC|MLO}.{jpg|jpeg|png}
```

**Examples:**
- `P1_L_DM_CC.jpg` - Patient 1, Left, Low Energy, Craniocaudal view
- `P1_L_CM_CC.jpg` - Patient 1, Left, Recombined, Craniocaudal view
- `P2_R_DM_MLO.png` - Patient 2, Right, Low Energy, Mediolateral oblique view

**Where:**
- `{patient}` = Patient number
- `{L|R}` = Laterality (Left or Right)
- `{DM|CM}` = Image type (DM=Direct/Low Energy, CM=Contrast/Recombined)
- `{CC|MLO}` = View (CC=Craniocaudal, MLO=Mediolateral Oblique)

## Artifact Types

| ID | Artifact Type |
|----|---------------|
| 1  | Breast in Breast |
| 2  | Skin Line / Thickening |
| 3  | Ripple (Motion) |
| 4  | Blood Vessels |
| 5  | Calcifications |
| 6  | Marker / Surgical Clip |
| 7  | Air Trapping / Skin Folds |
| 8  | Other |

## Workflow

### 1. Load Images
- Click "Browse" next to "Directory:" 
- Select folder containing paired DM/CM images
- Extension automatically pairs images by patient, laterality, and view

### 2. Review Each Image Pair
For each pair displayed:

**a) Indicate artifact presence:**
- Select "Yes" or "No" for **LE** (Low Energy/DM)
- Select "Yes" or "No" for **Recombined** (CM)

**b) If artifacts present, select types:**
- Check boxes for applicable artifacts on LE image
- Check boxes for applicable artifacts on Recombined image

**c) Optional: Add comments in "Other" text field**

### 3. Segment Artifacts (if "Yes" selected)
- Click **"Go to Segmentations"** button
- Extension creates color-coded segments automatically:
  - Red tones = LE artifacts
  - Blue tones = Recombined artifacts
- Use Paint/Draw tools to segment each artifact
- Click **"Continue to [Next Image]"** to switch between LE and Recombined
- Click **"Finish Segmentation"** when complete

### 4. Save and Continue
- Click **"Save, Open Next"** (Ctrl+Return / Cmd+Return)
- Annotations saved to `annotations.csv`
- Masks saved as `mask_{basename}_{DM|CM}.npy`

### 5. Review Mode (Optional)
- Check **"Review Mode"** checkbox before loading directory
- Allows viewing/editing previously annotated cases
- Loads existing masks and checkbox states

## Output Files

### annotations.csv
Comma-separated file with columns:
- `base_name` - Image identifier (e.g., "P1_L_CC")
- `artifact_type` - Classification (none/similar/only_dm/only_cm/both_different)
- `dm_artifacts` - List of LE artifacts
- `cm_artifacts` - List of Recombined artifacts  
- `other` - User comments
- `mask_path` - Path(s) to saved mask files
- `mask_status` - Mask save status

### Mask Files

**Combined masks (.npy):**
- `mask_P1_L_CC_DM.npy` - LE mask (width × height × 8 classes)
- `mask_P1_L_CC_CM.npy` - Recombined mask (width × height × 8 classes)

**Individual masks (.png):**
- `mask_P1_L_CC_DM_Breast_in_Breast.png`
- `mask_P1_L_CC_DM_Calcifications.png`
- etc.

## Keyboard Shortcuts

- **Ctrl+Return** (Windows/Linux) or **Cmd+Return** (Mac) - Save and open next

## Troubleshooting

### "No valid DM/CM image pairs found"
- Check image filenames match the naming convention
- Ensure both DM and CM images exist for each patient/view combination

### Segmentation not saving
- Make sure to click **"Finish Segmentation"** or **"Save Outline (Segmentation)"** button before saving annotations
- Check console for error messages

### Extension not loading
- Verify Slicer version ≤5.6.2 for full functionality
- Check module path is correctly added in Application Settings

### Masks appear empty after loading
- Ensure reference geometry matches between volume and segmentation
- Check .npy file was saved correctly (should not be all zeros)

## Known Limitations

- **Slicer version dependency**: Automatic artifact naming only works in Slicer 5.6.2 or earlier
- **2D images only**: Extension optimized for 2D mammography images
- **File format**: Currently supports JPG, JPEG, PNG (DICOM support via auto-detection)

## Logging

Activity logged to `cem_artifacts.log` in the image directory.

## Authors

- Donna Hooft
- Valentina Corbetta

## Acknowledgments

Based on framework by Anna Zapaishchykova and Vasco Prudente.

## License

[Add license information]

---

**For issues or questions, please contact [contact information]**