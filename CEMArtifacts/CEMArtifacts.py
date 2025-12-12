import logging
import os

import vtk
import pathlib
from pathlib import Path
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import ctk
import qt
from datetime import datetime
import SegmentStatistics
import logging
import re
#from qt import QtCore, QtGui

try:
    import pandas as pd
    import numpy as np
    import SimpleITK as sitk
except:
    slicer.util.pip_install('pandas')
    slicer.util.pip_install('numpy')
    slicer.util.pip_install('SimpleITK')
    
    import pandas as pd
    import numpy as np
    import SimpleITK as sitk
#
# SegmentationReview
#
#remove warnings
import warnings
warnings.filterwarnings("ignore")

class CEMArtifacts(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CEM Artifacts review"  
        self.parent.categories = ["Examples"]  
        self.parent.dependencies = []  
        self.parent.contributors = ["Donna Hooft;Valentina Corbetta"]  
        self.parent.helpText = """
Slicer3D extension for assesing presence of artifacts on recombined Contrast Enhanced Mammography (CEM) images and 
for segmentation of Artifacts which are not locally bound.
       """
        self.parent.acknowledgementText = """
This file was developed by Donna Hooft based on a github repository created by Anna Zapaishchykova and Vasco Prudente. 
"""
       


#
# CEMArtifactsWidget
#

class CEMArtifactsWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False


        # Changed to store pairs of volumes (DM and CM)
        self.volume_pairs = {}  # Maps view tag (e.g., "P1_L_CC") to {"DM": node, "CM": node}
        self.segmentation_node = None
        
        self.image_pairs = []  # List of paired image info dicts
        self.directory = None
        self.current_index = 0
        self.likert_scores = []
        self.n_pairs = 0
        
        

        self.volume_node = None
        self.nifti_files = []
        self.segmentation_files = []
        self.n_files = 0
        self.seg_mask_status = [] # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded, 3- mask edited
        self.with_mapper_flag = False
        self.id_subs = []
        self.id_subs_checked = []
        self.unique_case_flag=False
        self.finish_flag = False
        self._segmentation_update_timer = None  # Will be created in setup()


        self.pointListNode = None
        self.window_level = None   # To store current window/level settings
        self.segment_visiblity_states = {}  # Dictionary to store the visibility toggle of each segment
        self._is_loading = False # Flag to prevent re-entrance during loading





    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        import qSlicerSegmentationsModuleWidgetsPythonQt
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/CEMArtifacts.ui'))
        # --- Enable/disable artifact checkboxes based on Yes/No selection ---
        
        
        # Layout within the collapsible button
        parametersCollapsibleButton = ctk.ctkCollapsibleButton()
        parametersCollapsibleButton.text = "Input path" #establishes collapasbale button for input path
        self.layout.addWidget(parametersCollapsibleButton)

        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        parametersFormLayout = qt.QFormLayout(parametersCollapsibleButton)
        self.atlasDirectoryButton = ctk.ctkDirectoryButton() #lets you select path for pictures
        parametersFormLayout.addRow("Directory: ", self.atlasDirectoryButton) #Buttons for input path
        
        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)
        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = SlicerLikertDLratingLogic()

        # Connections
        #shortcut = qt.QShortcut(qt.QKeySequence("Ctrl+e"), slicer.util.mainWindow())
        #shortcut.connect("clicked(bool)", lambda: slicer.ui.radioButton_1.isChecked())
        # Get reference to the radio button widget 
        '''self.radioButton = self.ui.radioButton_1 
            # Create keyboard event handler
        def onKeyPress(event):
            key = event.key()
            if key == QtCore.Qt.Key_1:
                # Check the radio button
                self.radioButton.setChecked(True)
                    
        
        # Connect the keyboard handler 
        shortcut = QtGui.QShortcut(QtGui.QKeySequence("1"), self)
        shortcut.activated.connect(onKeyPress)'''

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        
        self.ui.PathLineEdit = ctk.ctkDirectoryButton()
        
        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.atlasDirectoryButton.directoryChanged.connect(self.onAtlasDirectoryChanged) #if changes, changes as wellloads im folder
        self.ui.save_and_next.connect('clicked(bool)', self.save_and_next_clicked) # saves and goes to next image
        self.ui.overwrite_mask.connect('clicked(bool)', self.overwrite_mask_clicked)    # overwrites the mask with the edited one
        
        # add a paint brush from segment editor window
        # Create a new segment editor widget and add it to the NiftyViewerWidget
        self._createSegmentEditorWidget_()
        
        # Connect new radio button groups
        self.ui.radioButton_dm_yes.toggled.connect(self.updateCheckboxVisibility)
        self.ui.radioButton_dm_no.toggled.connect(self.updateCheckboxVisibility)
        self.ui.radioButton_cm_yes.toggled.connect(self.updateCheckboxVisibility)
        self.ui.radioButton_cm_no.toggled.connect(self.updateCheckboxVisibility)

        # Create button groups for new radio buttons
        self.dmPresentGroup = qt.QButtonGroup()
        self.dmPresentGroup.addButton(self.ui.radioButton_dm_yes)
        self.dmPresentGroup.addButton(self.ui.radioButton_dm_no)
        self.dmPresentGroup.setExclusive(True)

        self.cmPresentGroup = qt.QButtonGroup()
        self.cmPresentGroup.addButton(self.ui.radioButton_cm_yes)
        self.cmPresentGroup.addButton(self.ui.radioButton_cm_no)
        self.cmPresentGroup.setExclusive(True)



        # --- Both Save buttons trigger the same action ---
        self.ui.save_and_next.clicked.connect(self.save_and_next_clicked)
        self.ui.quick_save_and_next.clicked.connect(self.save_and_next_clicked)

        # --- Keyboard shortcut for both (Ctrl/Command + Return) ---
        save_shortcut = qt.QShortcut(qt.QKeySequence("Ctrl+Return"), self.parent)
        save_shortcut.activated.connect(self.save_and_next_clicked)
        # macOS command key version
        save_shortcut_mac = qt.QShortcut(qt.QKeySequence("Meta+Return"), self.parent)
        save_shortcut_mac.activated.connect(self.save_and_next_clicked)

        # Connect artifact checkboxes with debouncing to avoid rapid re-triggering
        # self._segmentation_update_timer = qt.QTimer()
        # self._segmentation_update_timer.setSingleShot(True)
        # self._segmentation_update_timer.timeout.connect(self.setup_segmentation_for_current_selection)

        # for i in range(1, 10):
        #     getattr(self.ui, f"checkBox_dm_{i}").toggled.connect(
        #         lambda checked, timer=self._segmentation_update_timer: timer.start(300)
        #     )
        #     getattr(self.ui, f"checkBox_cm_{i}").toggled.connect(
        #         lambda checked, timer=self._segmentation_update_timer: timer.start(300)
        #     )


        self.updateCheckboxVisibility()  # initialize multiselect checkboxes

        
        #self.segmentEditorWidgetWidget.volumes.collapsed = True
         # Set parameter node first so that the automatic selections made when the scene is set are saved
            
        
        # Make sure parameter node is initialized (needed for module reload)
        #self.initializeParameterNode()


    def _createSegmentEditorWidget_(self): #this parts creates the segmentation bubblw and corresponding features
        """Create and initialize a customize Slicer Editor which contains just some the tools that we need for the segmentation"""

        import qSlicerSegmentationsModuleWidgetsPythonQt

        #advancedCollapsibleButton
        self.segmentEditorWidget = qSlicerSegmentationsModuleWidgetsPythonQt.qMRMLSegmentEditorWidget()
        #enable the "add" button
        #self.segmentEditorWidget.setAddSegmentShortcutEnabled(True)
        
        self.segmentEditorWidget.setMaximumNumberOfUndoStates(10) # 
        self.selectParameterNode()
        self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
        self.segmentEditorWidget.unorderedEffectsVisible = False
        self.segmentEditorWidget.setEffectNameOrder([
            'No editing','Threshold',
            'Paint', 'Draw', 
            'Erase','Level tracing',
            'Grow from seeds','Fill between slices',
            'Margin','Hollow',
            'Smoothing','Scissors',
            'Islands','Logical operators',
            'Mask volume'])
        
        # Add instructions label
        instructions = qt.QLabel(
            "<b>Segmentation Instructions:</b><br>"
            "1. Select artifact checkboxes to indicate which are present<br>"
            "2. Click 'Add' in Segment Editor to create a segment<br>"
            "3. Name segments EXACTLY as: <b>Artifact_Name_DM</b> or <b>Artifact_Name_CM</b><br>"
            "   Examples: 'Skin_Line_DM', 'Calcifications_CM'<br>"
            "   <b>For both_different:</b> Create separate segments for each image type<br>"
            "4. Paint the segmentation on the PRIMARY view<br>"
            "5. <b>IMPORTANT:</b> Click 'Save Outline' to save masks<br>"
            "6. Masks are saved separately for DM and CM based on segment names"
        )

        instructions.setWordWrap(True)
        instructions.setStyleSheet("QLabel { padding: 10px; border: 1px solid #cccc00; }")
        self.layout.addWidget(instructions)

        self.layout.addWidget(self.segmentEditorWidget) 

        # Hide the segmentation editor by default
        self.segmentEditorWidget.setVisible(False)
        # artifact_present = self.ui.radioButton_1.isChecked()
        # self.segmentEditorWidget.setVisible(artifact_present)
        # Observe editor effect registrations to make sure that any effects that are registered
        # later will show up in the segment editor widget. For example, if Segment Editor is set
        # as startup module, additional effects are registered after the segment editor widget is created.
        #self.effectFactorySingleton = slicer.qSlicerSegmentEditorEffectFactory.instance()
        #self.effectFactorySingleton.connect("effectRegistered(QString)", self.editorEffectRegistered)

        # Connect observers to scene events
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndImportEvent, self.onSceneEndImport)
        
    def enter(self):
        """Runs whenever the module is reopened"""
        #print("Enter")
        
        # Set parameter set node if absent
        self.selectParameterNode()
        if self.parameterSetNode:
            self.parameterSetNode.SetOverwriteMode(slicer.vtkMRMLSegmentEditorNode.OverwriteNone) #  heck fi this is neded really?
    
        self.segmentEditorWidget.updateWidgetFromMRML()

        # If no segmentation node exists then create one so that the user does not have to create one manually
        if not self.segmentEditorWidget.segmentationNodeID():
            #print("No segmentation node, creating one")
            self.segmentation_node = slicer.mrmlScene.GetFirstNode(None, "vtkMRMLSegmentationNode")
            if not self.segmentation_node:
                self.segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            self.segmentEditorWidget.setSegmentationNode(self.segmentation_node)
            if not self.segmentEditorWidget.sourceVolumeNodeID():
                self.sourceVolumeNodeID = self.getDefaultSourceVolumeNodeID()
                self.segmentEditorWidget.setSourceVolumeNodeID(self.sourceVolumeNodeID)
        self.initializeParameterNode()
    
    def updateCheckboxVisibility(self):
        """Control visibility of artifact selection UI based on DM/CM artifact presence"""
        dm_artifacts_present = self.ui.radioButton_dm_yes.isChecked()
        cm_artifacts_present = self.ui.radioButton_cm_yes.isChecked()
        dm_no_artifacts = self.ui.radioButton_dm_no.isChecked()
        cm_no_artifacts = self.ui.radioButton_cm_no.isChecked()
        
        # Show/hide DM artifact checkboxes
        self.ui.buttongroup_dm.setVisible(dm_artifacts_present)
        
        # Show/hide CM artifact checkboxes
        self.ui.buttongroup_cm.setVisible(cm_artifacts_present)
        
        # Hide the original artifact group (not needed in new logic)
        # self.ui.buttongroup.setVisible(False)
        
        # Show quick save button only if both are "No"
        both_no_artifacts = dm_no_artifacts and cm_no_artifacts
        self.ui.quick_save_and_next.setVisible(both_no_artifacts)
        
        # Enable/disable DM checkboxes
        for i in range(1, 10):
            getattr(self.ui, f"checkBox_dm_{i}").setEnabled(dm_artifacts_present)
        
        # Enable/disable CM checkboxes
        for i in range(1, 10):
            getattr(self.ui, f"checkBox_cm_{i}").setEnabled(cm_artifacts_present)
        
        # Show/hide the segmentation editor (only if any artifacts present)
        any_artifacts = dm_artifacts_present or cm_artifacts_present
        self.segmentEditorWidget.setVisible(any_artifacts)
        
        # Show/hide the "Save Outline" button
        self.ui.overwrite_mask.setVisible(any_artifacts)
        
        # Setup segmentation when visibility changes
        # if any_artifacts:
        #     self.setup_segmentation_for_current_selection()
        # Create segmentation node when artifacts are indicated
        if any_artifacts:
            print(f"[DEBUG] Artifacts present, ensuring segmentation node exists")
            self._ensure_segmentation_node_exists()
        else:
            print(f"[DEBUG] No artifacts indicated")

    def _ensure_segmentation_node_exists(self):
        """Create a segmentation node if one doesn't exist"""
        if not self.segmentation_node or not slicer.mrmlScene.IsNodePresent(self.segmentation_node):
            print(f"[DEBUG] Creating new segmentation node")
            current_pair = self.image_pairs[self.current_index]
            self.segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            self.segmentation_node.SetName(f"{current_pair['base_name']}_segmentation")
            self.segmentation_node.CreateDefaultDisplayNodes()
            
            # Set reference geometry from DM volume (default)
            dm_volume = self.volume_pairs[current_pair['base_name']]['DM']
            self.segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(dm_volume)
            
            # Connect to segment editor
            self.segmentEditorWidget.setSegmentationNode(self.segmentation_node)
            self.segmentEditorWidget.setSourceVolumeNode(dm_volume)
            
            print(f"[DEBUG] Created segmentation node: {self.segmentation_node.GetName()}")
        else:
            print(f"[DEBUG] Segmentation node already exists: {self.segmentation_node.GetName()}")

    def overwrite_mask_clicked(self):
        """Save segmentation as numpy array (always 9 classes) and individual PNG files - separately for DM and CM"""

        # Get the active segmentation from the segment editor
        if self.segmentEditorWidget.segmentationNode():
            self.segmentation_node = self.segmentEditorWidget.segmentationNode()
            print(f"[DEBUG] Got segmentation from editor: {self.segmentation_node.GetName()}")
        else:
            print(f"[DEBUG] No segmentation in editor widget")
        
        # Check if we have a segmentation
        if not self.segmentation_node:
            print(f"[DEBUG] self.segmentation_node is None!")
            slicer.util.warningDisplay("No segmentation to save! Please create at least one segment first.")
            return
        
        # Check if segmentation has any segments
        segmentation = self.segmentation_node.GetSegmentation()
        num_segments = segmentation.GetNumberOfSegments()
        segment_ids = [segmentation.GetNthSegmentID(i) for i in range(num_segments)]

        for i in range(num_segments):
            seg_id = segmentation.GetNthSegmentID(i)
            segment = segmentation.GetSegment(seg_id)
            seg_name = segment.GetName()
            if not (seg_name.endswith('_DM') or seg_name.endswith('_CM')):
                slicer.util.warningDisplay(
                    f"Segment '{seg_name}' must end with '_DM' or '_CM'!\n\n"
                    f"Please rename your segments according to the convention:\n"
                    f"Artifact_Name_DM or Artifact_Name_CM\n\n"
                    f"Example: 'Skin_Line_DM', 'Calcifications_CM'"
                )
                return
        
        print(f"[DEBUG] Number of segments in segmentation: {num_segments}")
        
        if num_segments == 0:
            print(f"[DEBUG] Segmentation exists but has no segments!")
            slicer.util.warningDisplay("No segments found! Please create at least one segment first.")
            return
        
        current_pair = self.image_pairs[self.current_index]
        base_name = current_pair['base_name']
        
        # Determine artifact type based on current selections
        dm_artifacts_present = self.ui.radioButton_dm_yes.isChecked()
        cm_artifacts_present = self.ui.radioButton_cm_yes.isChecked()
        
        if not dm_artifacts_present and not cm_artifacts_present:
            slicer.util.warningDisplay("No artifacts selected to save!")
            return
   
        print(f"[DEBUG] Number of segments: {num_segments}")
        for idx, seg_id in enumerate(segment_ids):
            print(f"[DEBUG] Segment {idx}: ID={seg_id}")
        
        # CORRECT - checks name:
        dm_segment_ids = []
        cm_segment_ids = []
        shared_segment_ids = []

        for seg_id in segment_ids:
            segment = segmentation.GetSegment(seg_id)
            seg_name = segment.GetName()
            if seg_name.endswith('_DM'):
                dm_segment_ids.append(seg_id)
            elif seg_name.endswith('_CM'):
                cm_segment_ids.append(seg_id)
            else:
                shared_segment_ids.append(seg_id)
        
        print(f"[DEBUG] DM segments: {dm_segment_ids}")
        print(f"[DEBUG] CM segments: {cm_segment_ids}")
        print(f"[DEBUG] Shared segments: {shared_segment_ids}")
        
        # Map segment names to artifact class indices (0-8 for artifacts 1-9)
        artifact_name_to_id = {
            "Breast_in_Breast": 1,
            "Skin_Line": 2,
            "Ripple_Motion": 3,
            "Blood_Vessels": 4,
            "Calcifications": 5,
            "Surgical_Clip": 6,
            "Air_Trapping": 7,
            "Contrast_Splatter": 8,
            "Other": 9
        }
        
        
        # Helper function to save masks for a specific image type
        
        def save_masks_for_type(segment_ids_to_process, suffix, ref_volume):
            if not segment_ids_to_process:
                print(f"[DEBUG] No segments to process for suffix '{suffix}'")
                return None
            
            # Get image dimensions from reference volume
            dims = ref_volume.GetImageData().GetDimensions()
            image_height, image_width = dims[1], dims[0]
            
            print(f"[DEBUG] Using reference volume dimensions for {suffix}: width={image_width}, height={image_height}")
            
            # Initialize combined mask array with 9 classes (width, height, 9)
            combined_mask = np.zeros((image_width, image_height, 9), dtype=np.uint8)
            
            # Process each segment individually to preserve overlaps
            for seg_id in segment_ids_to_process:
                segment = segmentation.GetSegment(seg_id)
                segment_name = segment.GetName()
                
                print(f"\n[DEBUG] Processing segment '{segment_name}'")
                
                # Extract the base artifact name
                base_artifact_name = segment_name.replace("_DM", "").replace("_CM", "")
                print(f"[DEBUG] Base artifact name: '{base_artifact_name}'")
                
                # Find which artifact class this segment belongs to
                artifact_id = artifact_name_to_id.get(base_artifact_name)
                print(f"[DEBUG] Artifact ID from mapping: {artifact_id}")
                
                if artifact_id is None:
                    print(f"[DEBUG] WARNING: Artifact name '{base_artifact_name}' not found in mapping!")
                    continue
                
                class_idx = artifact_id - 1  # Convert to 0-indexed
                print(f"[DEBUG] Class index: {class_idx}")
                
                # Create a temporary segmentation with ONLY this segment
                temp_seg_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
                temp_seg_node.SetName(f"temp_seg_{segment_name}")
                temp_seg_node.SetReferenceImageGeometryParameterFromVolumeNode(ref_volume)
                
                # Copy only this one segment
                temp_seg_node.GetSegmentation().CopySegmentFromSegmentation(segmentation, seg_id)
                
                # Export THIS SINGLE segment to labelmap
                temp_labelmap = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
                temp_labelmap.SetName(f"temp_labelmap_{segment_name}")
                
                # Export single segment
                slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(
                    temp_seg_node, temp_labelmap, slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY
                )
                
                # Get the labelmap array
                labelmap_array = slicer.util.arrayFromVolume(temp_labelmap)
                
                print(f"[DEBUG] Labelmap array shape: {labelmap_array.shape}")
                print(f"[DEBUG] Labelmap unique values: {np.unique(labelmap_array)}")
                
                # Extract binary mask for this segment (any non-zero value = 1)
                mask_slice = (labelmap_array[0, :, :] > 0).astype(np.uint8)
                print(f"[DEBUG] Mask slice shape: {mask_slice.shape}, non-zero: {np.count_nonzero(mask_slice)}")
                
                # Transpose to match (width, height) orientation
                mask_slice_transposed = mask_slice.T
                print(f"[DEBUG] After transpose shape: {mask_slice_transposed.shape}, non-zero: {np.count_nonzero(mask_slice_transposed)}")
                
                # ADD to combined mask (use logical OR to preserve overlaps)
                combined_mask[:, :, class_idx] = np.logical_or(
                    combined_mask[:, :, class_idx], 
                    mask_slice_transposed
                ).astype(np.uint8)
                print(f"[DEBUG] Stored in combined_mask[:, :, {class_idx}]")
                
                # Clean up temporary nodes
                slicer.mrmlScene.RemoveNode(temp_labelmap)
                slicer.mrmlScene.RemoveNode(temp_seg_node)
            
            # Debug: Check combined mask contents
            print(f"\n[DEBUG] Combined mask summary for {suffix}:")
            for class_idx in range(9):
                non_zero = np.count_nonzero(combined_mask[:, :, class_idx])
                print(f"[DEBUG] Class {class_idx} ({self._get_artifact_name(class_idx + 1)}): {non_zero} non-zero pixels")
            
            # Save combined .npy file
            npy_filename = f"mask_{base_name}{suffix}.npy"
            npy_path = os.path.join(self.directory, npy_filename)
            # Rotate 90 degrees counterclockwise for each channel
            combined_mask_rotated = np.rot90(combined_mask, k=1, axes=(0, 1))
            np.save(npy_path, combined_mask_rotated)
            logging.getLogger('CEMArtifacts').info(f"Saved combined mask: {npy_path}")
            print(f"[DEBUG] Saved .npy file (rot90): {npy_path}")
            
            # Save individual PNG files for each artifact that has content
            try:
                from PIL import Image
            except ImportError:
                slicer.util.pip_install('pillow')
                from PIL import Image
            
            print(f"\n[DEBUG] Attempting to save PNG files for {suffix}:")
            for class_idx in range(9):
                artifact_name = self._get_artifact_name(class_idx + 1)
                has_content = combined_mask[:, :, class_idx].any()
                print(f"[DEBUG] Class {class_idx} ({artifact_name}): has_content={has_content}")
                
                if has_content:
                    png_filename = f"mask_{base_name}{suffix}_{artifact_name}.png"
                    png_path = os.path.join(self.directory, png_filename)
                    print(f"[DEBUG] Saving PNG: {png_filename}")
                    
                    # Convert to PIL Image and save (multiply by 255 for visibility)
                    mask_data = combined_mask[:, :, class_idx] * 255
                    print(f"[DEBUG] Mask data range: min={mask_data.min()}, max={mask_data.max()}")
                    
                    # Transpose and flip vertically
                    mask_data_transposed = mask_data.T
                    mask_data_flipped = np.flipud(mask_data_transposed)
                    
                    mask_img = Image.fromarray(mask_data_flipped.astype(np.uint8))
                    print(f"[DEBUG] PIL Image size: {mask_img.size}, mode: {mask_img.mode}")
                    
                    mask_img.save(png_path)
                    print(f"[DEBUG] Successfully saved (flipped): {png_path}")
                    logging.getLogger('CEMArtifacts').info(f"Saved individual mask: {png_filename}")
            
            return npy_path
        # Save DM masks if DM artifacts present
        saved_paths = []
        if dm_artifacts_present and (dm_segment_ids or shared_segment_ids):
            dm_ref_volume = self.volume_pairs[current_pair['base_name']]['DM']
            segments_to_save = dm_segment_ids + shared_segment_ids
            dm_path = save_masks_for_type(segments_to_save, "_DM", dm_ref_volume)
            if dm_path:
                saved_paths.append(os.path.basename(dm_path))
                current_pair['masks']['DM'] = dm_path
        
        # Save CM masks if CM artifacts present
        if cm_artifacts_present and (cm_segment_ids or shared_segment_ids):
            cm_ref_volume = self.volume_pairs[current_pair['base_name']]['CM']
            segments_to_save = cm_segment_ids + shared_segment_ids
            cm_path = save_masks_for_type(segments_to_save, "_CM", cm_ref_volume)
            if cm_path:
                saved_paths.append(os.path.basename(cm_path))
                current_pair['masks']['CM'] = cm_path
        
        
        if saved_paths:
            slicer.util.infoDisplay(f"Segmentation saved successfully:\n" + "\n".join(saved_paths) + "\nand individual PNG files")
        else:
            slicer.util.warningDisplay("No masks were saved. Please check segment names.")


    def joinpath(self, rootdir, filename):
        return os.path.join(rootdir, filename)
        
    def _construct_full_path(self, path):
        if os.path.isabs(path):
            return path
        else:
            return self.joinpath(self.directory, path)

    def _is_valid_extension(self, path):
        # First check normal image extensions
        valid_ext = [".nii", ".nii.gz", ".nrrd", ".jpg", ".jpeg", ".tif", ".tiff", ".dcm"]
        lower = path.lower()

        if any(lower.endswith(ext) for ext in valid_ext):
            return True

        # --- Now detect DICOM files with no extension ---
        try:
            with open(path, "rb") as f:
                f.seek(128)
                is_dicom = f.read(4) == b"DICM"
            return is_dicom
        except:
            return False

    def _parse_filename(self, filename):
        """
        Parse filename like P1_L_DM_CC.jpg or P1_R_CM_MLO.jpg
        Returns dict with patient, laterality, image_type, view
        """
        pattern = r'P(\d+)_([LR])_(DM|CM)_(CC|MLO)'
        match = re.match(pattern, filename, re.IGNORECASE)
        
        if match:
            return {
                'patient': match.group(1),
                'laterality': match.group(2).upper(),
                'image_type': match.group(3).upper(),
                'view': match.group(4).upper(),
                'filename': filename
            }
        return None
    
    def _group_image_pairs(self, files):
        """
        Group DM and CM images into pairs based on patient, laterality, and view.
        Returns list of dicts with 'DM' and 'CM' file paths.
        """
        parsed_files = []
        for f in files:
            parsed = self._parse_filename(os.path.basename(f))
            if parsed:
                parsed['full_path'] = f
                parsed_files.append(parsed)
        
        # Group by patient_laterality_view
        pairs_dict = {}
        for pf in parsed_files:
            key = f"P{pf['patient']}_{pf['laterality']}_{pf['view']}"
            if key not in pairs_dict:
                pairs_dict[key] = {'base_name': key, 'patient': pf['patient'], 
                                'laterality': pf['laterality'], 'view': pf['view']}
            
            pairs_dict[key][pf['image_type']] = pf['full_path']
        
        # Only keep complete pairs (both DM and CM)
        complete_pairs = []
        for key, pair_info in pairs_dict.items():
            if 'DM' in pair_info and 'CM' in pair_info:
                # ADD MASK DETECTION HERE
                pair_info['masks'] = self._find_masks_for_pair(pair_info)
                complete_pairs.append(pair_info)
        
        # Sort by patient number, laterality, then view
        complete_pairs.sort(key=lambda x: (int(x['patient']), x['laterality'], x['view']))
        
        return complete_pairs

    # ADD THESE NEW METHODS HERE:

    def _find_masks_for_pair(self, pair_info):
        """Find existing masks for a DM/CM pair - looking for .npy combined masks"""
        base_name = pair_info['base_name']
        directory = self.directory
        
        masks = {
            'DM': None,
            'CM': None,
            'shared': None
        }
        
        # Look for .npy masks: mask_P1_L_MLO_DM.npy, mask_P1_L_MLO_CM.npy
        for suffix, key in [('_DM', 'DM'), ('_CM', 'CM'), ('', 'shared')]:
            mask_path = os.path.join(directory, f"mask_{base_name}{suffix}.npy")
            if os.path.exists(mask_path):
                masks[key] = mask_path
                logging.getLogger('CEMArtifacts').info(f'Found {key} mask: {mask_path}')
        
        return masks

    def _get_artifact_name(self, artifact_id):
        """Get artifact name from ID"""
        mapping = {
            1: "Breast_in_Breast",
            2: "Skin_Line",
            3: "Ripple_Motion",
            4: "Blood_Vessels",
            5: "Calcifications",
            6: "Surgical_Clip",
            7: "Air_Trapping",
            8: "Contrast_Splatter",
            9: "Other"
        }
        return mapping.get(artifact_id, f"Artifact_{artifact_id}")
    
    def _save_empty_mask(self, base_name, suffix):
        """Save an empty mask (all zeros) for cases with no artifacts"""
        current_pair = self.image_pairs[self.current_index]
        
        # Determine which volume to use as reference
        if suffix == "_CM":
            ref_volume = self.volume_pairs[base_name]['CM']
        else:
            ref_volume = self.volume_pairs[base_name]['DM']
        
        # Get image dimensions
        dims = ref_volume.GetImageData().GetDimensions()
        
        # Create empty mask array (width, height, 9)
        combined_mask = np.zeros((dims[0], dims[1], 9), dtype=np.uint8)
        
        # Save as .npy
        npy_filename = f"mask_{base_name}{suffix}.npy"
        npy_path = os.path.join(self.directory, npy_filename)
        np.save(npy_path, combined_mask)
        
        logging.getLogger('CEMArtifacts').info(f"Saved empty mask: {npy_path}")
        return npy_path


    def create_segments_for_artifacts(self, artifact_type, dm_artifacts=None, cm_artifacts=None):
        """Create segments with proper naming based on artifact selection"""
        
        if not self.segmentation_node:
            self.segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            current_pair = self.image_pairs[self.current_index]
            self.segmentation_node.SetName(f"{current_pair['base_name']}_segmentation")
            # Ensure display node is created
            self.segmentation_node.CreateDefaultDisplayNodes()
        
        # Clear existing segments
        segmentation = self.segmentation_node.GetSegmentation()
        segmentation.RemoveAllSegments()
        
        # Helper for naming
        def add_segment(artifact_id, suffix=None):
            base = self._get_artifact_name(artifact_id)
            name = base if suffix is None else f"{base}_{suffix}"
            segment_id = segmentation.AddEmptySegment(name)
        
            # Ensure display properties are initialized for this segment
            if self.segmentation_node.GetDisplayNode():
                display_node = self.segmentation_node.GetDisplayNode()
                # Force creation of display properties for new segment
                display_node.SetSegmentVisibility(segment_id, True)
                display_node.SetSegmentOpacity(segment_id, 0.5)

        # Similar on both images
        if artifact_type == "similar":
            for a in dm_artifacts or []:
                add_segment(a)

        # Only DM artifacts
        elif artifact_type == "only_dm":
            for a in dm_artifacts or []:
                add_segment(a, "DM")

        # Only CM artifacts
        elif artifact_type == "only_cm":
            for a in cm_artifacts or []:
                add_segment(a, "CM")

        # Both different
        elif artifact_type == "both_different":
            for a in dm_artifacts or []:
                add_segment(a, "DM")
            for a in cm_artifacts or []:
                add_segment(a, "CM")

        logging.getLogger('CEMArtifacts').info(f"Created segments for {artifact_type}")
        return True


    def load_existing_mask(self, mask_info, artifact_type):
        """Load existing mask from .npy file (always 9 classes) and reconstruct segmentation"""
        
        # Determine which mask file to load based on what's available
        mask_path = None
        
        # Priority: try to find the most relevant mask
        if artifact_type == "similar":
            mask_path = mask_info.get('shared') or mask_info.get('DM') or mask_info.get('CM')
        elif artifact_type == "only_dm":
            mask_path = mask_info.get('DM') or mask_info.get('shared')
        elif artifact_type == "only_cm":
            mask_path = mask_info.get('CM') or mask_info.get('shared')
        elif artifact_type == "both_different":
            # For both_different, we need both masks - don't load old masks
            mask_path = None
        
        if not mask_path or not os.path.exists(mask_path) or not mask_path.endswith('.npy'):
            return False
        
        try:
            # Load numpy array (should be width, height, 9)
            combined_mask = np.load(mask_path)
            
            # Check if mask is all zeros (no artifacts)
            if not combined_mask.any():
                logging.getLogger('CEMArtifacts').info(f"Mask is empty (no artifacts): {mask_path}")
                return False
            
            # Remove old segmentation node if it exists
            if self.segmentation_node and slicer.mrmlScene.IsNodePresent(self.segmentation_node):
                slicer.mrmlScene.RemoveNode(self.segmentation_node)
                self.segmentation_node = None

            # Create new segmentation node
            self.segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            current_pair = self.image_pairs[self.current_index]
            self.segmentation_node.SetName(f"{current_pair['base_name']}_segmentation")

            # Create display node BEFORE adding segments
            self.segmentation_node.CreateDefaultDisplayNodes()
            
            # Get reference volume
            if artifact_type in ["similar", "only_dm", "both_different"]:
                ref_volume = self.volume_pairs[current_pair['base_name']]['DM']
            else:
                ref_volume = self.volume_pairs[current_pair['base_name']]['CM']
            
            # Set reference geometry
            self.segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(ref_volume)
            
            # Get image dimensions
            dims = ref_volume.GetImageData().GetDimensions()
            
            # Process each of the 9 artifact classes
            for class_idx in range(9):
                # Extract mask for this class (transpose back from width,height to match image orientation)
                class_mask = combined_mask[:, :, class_idx].T
                
                # Skip if mask is empty for this class
                if not class_mask.any():
                    continue
                
                # Get artifact name for this class
                artifact_name = self._get_artifact_name(class_idx + 1)
                
                # Determine segment name based on artifact type
                if artifact_type == "only_dm":
                    segment_name = f"{artifact_name}_DM"
                elif artifact_type == "only_cm":
                    segment_name = f"{artifact_name}_CM"
                else:
                    segment_name = artifact_name
                
                # Create temporary labelmap for this segment
                temp_labelmap = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
                temp_labelmap.SetAndObserveImageData(ref_volume.GetImageData())
                
                # Create array with correct dimensions [slices, rows, cols]
                labelmap_array = np.zeros((1, dims[1], dims[0]), dtype=np.uint8)
                labelmap_array[0, :, :] = class_mask
                
                # Update the labelmap
                slicer.util.updateVolumeFromArray(temp_labelmap, labelmap_array)
                temp_labelmap.SetOrigin(ref_volume.GetOrigin())
                temp_labelmap.SetSpacing(ref_volume.GetSpacing())
                # Copy the IJK to RAS matrix
                mat = vtk.vtkMatrix4x4()
                ref_volume.GetIJKToRASMatrix(mat)
                temp_labelmap.SetIJKToRASMatrix(mat)
                # Import to segmentation
                slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                    temp_labelmap, self.segmentation_node, [segment_name]
                )

                # Ensure display properties are set for imported segment
                if self.segmentation_node.GetDisplayNode():
                    display_node = self.segmentation_node.GetDisplayNode()
                    # Get the actual segment ID that was created
                    segmentation = self.segmentation_node.GetSegmentation()
                    actual_segment_id = segmentation.GetSegmentIdBySegmentName(segment_name)
                    if actual_segment_id:
                        display_node.SetSegmentVisibility(actual_segment_id, True)
                        display_node.SetSegmentOpacity(actual_segment_id, 0.5)

                # Clean up
                slicer.mrmlScene.RemoveNode(temp_labelmap)
            
            logging.getLogger('CEMArtifacts').info(f"Loaded existing mask from: {mask_path}")
            return True
            
        except Exception as e:
            logging.getLogger('CEMArtifacts').error(f"Failed to load mask from {mask_path}: {e}")
            return False

    def setup_segmentation_for_current_selection(self):
        """Setup segmentation based on current artifact selections"""
        
        # Prevent re-entrance during loading
        if self._is_loading:
            return
        
        # Get artifact presence status
        dm_artifacts_present = self.ui.radioButton_dm_yes.isChecked()
        cm_artifacts_present = self.ui.radioButton_cm_yes.isChecked()
        
        if not dm_artifacts_present and not cm_artifacts_present:
            # Hide segmentation editor if no artifacts
            self.segmentEditorWidget.setVisible(False)
            return
        
        # Collect selected artifacts
        dm_artifacts = []
        cm_artifacts = []
        artifact_type = None
        
        if dm_artifacts_present:
            for i in range(1, 10):
                if getattr(self.ui, f"checkBox_dm_{i}").isChecked():
                    dm_artifacts.append(i)
        
        if cm_artifacts_present:
            for i in range(1, 10):
                if getattr(self.ui, f"checkBox_cm_{i}").isChecked():
                    cm_artifacts.append(i)
        
        # Determine artifact type
        if dm_artifacts and cm_artifacts:
            if set(dm_artifacts) == set(cm_artifacts):
                artifact_type = "similar"
            else:
                artifact_type = "both_different"
        elif dm_artifacts:
            artifact_type = "only_dm"
        elif cm_artifacts:
            artifact_type = "only_cm"
        else:
            # Artifacts indicated but none selected yet - don't setup segmentation
            return
        
        # **STORE CURRENT SLICE POSITIONS**
        lm = slicer.app.layoutManager()
        stored_positions = {}
        for view_name in ["Red", "Yellow"]:
            sw = lm.sliceWidget(view_name)
            if sw:
                slice_node = sw.sliceLogic().GetSliceNode()
                stored_positions[view_name] = {
                    'offset': slice_node.GetSliceOffset(),
                    'fov': list(slice_node.GetFieldOfView())
                }
        
        # Check for existing mask
        current_pair = self.image_pairs[self.current_index]
        mask_info = current_pair.get('masks', {})
        
        # Try to load existing mask
        mask_loaded = False
        if mask_info:
            mask_loaded = self.load_existing_mask(mask_info, artifact_type)
        
        if not mask_loaded:
            # Create new segments only if no mask was loaded
            self.create_segments_for_artifacts(artifact_type, dm_artifacts, cm_artifacts)
        
        # Setup segment editor widget
        if self.segmentation_node:
            self.segmentEditorWidget.setSegmentationNode(self.segmentation_node)
            
            # Set source volume based on artifact type
            target_volume = None
            try:
                if artifact_type in ["similar", "only_dm", "both_different"]:
                    target_volume = self.volume_pairs[current_pair['base_name']]['DM']
                elif artifact_type == "only_cm":
                    target_volume = self.volume_pairs[current_pair['base_name']]['CM']
                print(target_volume)
                if target_volume:
                    self.segmentEditorWidget.setSourceVolumeNode(target_volume)
                    # CRITICAL: Set reference geometry based on primary volume
                    # This ensures all segments use consistent coordinate system
                    self.segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(target_volume)
                
                self.segmentEditorWidget.setVisible(True)
            except KeyError as e:
                logging.getLogger('CEMArtifacts').error(f"Volume not found: {e}")
                return
        
        # **RESTORE SLICE POSITIONS**
        qt.QTimer.singleShot(50, lambda: self._restore_slice_positions(stored_positions))

    def _restore_slice_positions(self, stored_positions):
        """Restore slice positions after segmentation updates"""
        lm = slicer.app.layoutManager()
        for view_name, position_info in stored_positions.items():
            sw = lm.sliceWidget(view_name)
            if sw:
                slice_node = sw.sliceLogic().GetSliceNode()
                slice_node.SetSliceOffset(position_info['offset'])
                fov = position_info['fov']
                slice_node.SetFieldOfView(fov[0], fov[1], fov[2])
                sw.sliceLogic().SnapSliceOffsetToIJK()
    


    
    def _restore_index(self, ann_csv, files_list, mask_list, mask_status_list=None):
        #print(files_list,mask_list)
        #print(self.unique_case_flag)
        #ann_csv {[self.nifti_files[self.current_index]],[likert_score],[self.ui.comment.toPlainText()]}
        statuses, unchecked_files, unchecked_masks, checked_ids, id_subs_list = [], [], [], [], []
        list_of_checked = ann_csv['file'].values
        list_of_checked = [self._construct_full_path(i) for i in list_of_checked]
        
        list_of_checked_masks = ann_csv['mask_path'].values
        #print(list_of_checked)
        # check if ['mask_path'] is empty
        if type(list_of_checked_masks[0]) == str:
            list_of_checked_masks = [self._construct_full_path(i) for i in list_of_checked_masks]
        
        #find subset of files that are not checked
        if self.unique_case_flag:
            # read what ids were checked by finding the corresponding ids
            checked_ids = []
            list_of_checked = ann_csv['file'].values
            # first, check what ids were checked
            for id_subj, img, _ in zip(self.mappings["subj_id"], self.mappings["img_path"], self.mappings["mask_path"]):
                if img in list_of_checked:
                    checked_ids.append(id_subj)
            # second, find the files that were not checked       
            for id_subj, img, mask in zip(self.mappings["subj_id"], self.mappings["img_path"], self.mappings["mask_path"]):
                if id_subj not in checked_ids:
                    id_subs_list.append(id_subj)
                    unchecked_files.append(self._construct_full_path(img))
                    # check if mask is empty or nan 
                    if type(mask) == str:
                        unchecked_masks.append(self._construct_full_path(mask))
                        statuses.append(2)
                    else:
                        unchecked_masks.append("")
                        statuses.append(0)
                        
            #print("Checked ids",checked_ids)
            #print("Unchecked files",unchecked_files)
            #print("Unchecked masks",unchecked_masks)
            
        else:
            for i in range(len(files_list)):
                if files_list[i] not in list_of_checked:
                    unchecked_files.append(files_list[i])
                    unchecked_masks.append(mask_list[i])
                    statuses.append(mask_status_list[i])
        
        
        #return list of unchecked files
        return unchecked_files, unchecked_masks, statuses, id_subs_list, checked_ids
    
    def getDefaultSourceVolumeNodeID(self):
        layoutManager = slicer.app.layoutManager()
        firstForegroundVolumeID = None
        # Use first background volume node in any of the displayed layouts.
        # If no beackground volume node is in any slice view then use the first
        # foreground volume node.
        for sliceViewName in layoutManager.sliceViewNames():
            sliceWidget = layoutManager.sliceWidget(sliceViewName)
            if not sliceWidget:
                continue
            compositeNode = sliceWidget.mrmlSliceCompositeNode()
            if compositeNode.GetBackgroundVolumeID():
                return compositeNode.GetBackgroundVolumeID()
            if compositeNode.GetForegroundVolumeID() and not firstForegroundVolumeID:
                firstForegroundVolumeID = compositeNode.GetForegroundVolumeID()
        # No background volume was found, so use the foreground volume (if any was found)
        return firstForegroundVolumeID 
   
    def editorEffectRegistered(self):
        self.segmentEditorWidget.updateEffectList()
        
    def selectParameterNode(self):
        # Select parameter set node if one is found in the scene, and create one otherwise
        segmentEditorSingletonTag = "SegmentEditor"
        segmentEditorNode = slicer.mrmlScene.GetSingletonNode(segmentEditorSingletonTag, "vtkMRMLSegmentEditorNode")
        if segmentEditorNode is None:
            segmentEditorNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentEditorNode")
            segmentEditorNode.UnRegister(None)
            segmentEditorNode.SetSingletonTag(segmentEditorSingletonTag)
            segmentEditorNode = slicer.mrmlScene.AddNode(segmentEditorNode)
        #if self.parameterSetNode == segmentEditorNode:
        #    # nothing changed
        #    return
        self.parameterSetNode = segmentEditorNode
        self.parameterSetNode.SetOverwriteMode(slicer.vtkMRMLSegmentEditorNode.OverwriteNone)
    
        self.segmentEditorWidget.setMRMLSegmentEditorNode(self.parameterSetNode)
   
    def onAtlasDirectoryChanged(self, directory):
        """these parts have the be changes since now autmatic masks are mtacthed with their nifitt, mine do not have segmentations yet (maybe some already do ifi in process)
        also 2d data, how is this handeled differently , does it need ot be handled in """
        
        self.directory = os.path.normpath(directory)
        directory = self.directory
        logger = logging.getLogger('CEMArtifacts')
        logger.setLevel(logging.DEBUG)

        # Set up logging to file
        fileHandler = logging.FileHandler(self.joinpath(directory,'cem_artifacts.log'))
        fileHandler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(fileHandler) 
        
        try:
            # Clear existing volumes
            for pair in self.volume_pairs.values():
                for vol in pair.values():
                    if vol:
                        slicer.mrmlScene.RemoveNode(vol)
            self.volume_pairs = {}
            
            if self.segmentation_node:
                slicer.mrmlScene.RemoveNode(self.segmentation_node)
        except:
            pass
        
        # self.unique_case_flag=False

        mapping_unique = os.path.join(directory, "mapping_unique.csv")
        mapping_file = os.path.join(directory, "mapping.csv")
        # case 0: searching for one unique nifti file for id
        # they 




        if os.path.isfile(mapping_unique):
            case_flag = True
            # mapping file contains id and nifti file name
            id_subs = []
            self.mappings = pd.read_csv(self.joinpath(directory,"mapping_unique.csv"))
            self.unique_case_flag = True
            for id_subj, img, mask in zip(self.mappings["subj_id"], self.mappings["img_path"], self.mappings["mask_path"]):
                # counting images
                if os.path.exists(self.joinpath(directory,img)) and self._is_valid_extension(self.joinpath(directory,img)):
                    self.nifti_files.append(self.joinpath(directory,img))
                    id_subs.append(id_subj)
                    # counting masks
                    # check if mask is 
                    if type(mask) == str:
                        if os.path.exists(self.joinpath(directory,mask)) and self._is_valid_extension(self.joinpath(directory,mask)):
                            
                            self.segmentation_files.append(self.joinpath(directory,mask))
                            self.seg_mask_status.append(2) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'Found mask for {img}')
                        elif self._is_valid_extension(self.joinpath(directory,mask)) and not os.path.exists(self.joinpath(directory,mask)):
                           
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(1) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'Cannot load mask for {img}, check path')
                        else:
                            
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(0) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'No mask provided for {img}')
                    else:
                        
                        self.segmentation_files.append("")
                        self.seg_mask_status.append(0)
                        logger.info(f'No mask provided for {img}')
                else:
                    logger.info(f'File {img} does not exist or has wrong extension, skipping')
            #get unique ids
            self.id_subs = id_subs
            #print("Unique:",len(np.unique(self.id_subs)),id_subs)   
        
        # case 1: mapper cvs is present
        elif os.path.isfile(mapping_file):
            logger.info('Found mappings between files and masks') 
            #print("Found mappings between files and masks")
            self.mappings = pd.read_csv(self.joinpath(directory,"mapping.csv"))
            self.with_mapper_flag = True
            # casting to zero all nan values
            
            #print("Loaded mappings between files and masks")
            for img, mask in zip(self.mappings["img_path"], self.mappings["mask_path"]):
                # counting images
                if os.path.exists(self.joinpath(directory,img)) and self._is_valid_extension(self.joinpath(directory,img)):
                    self.nifti_files.append(self.joinpath(directory,img))
                    # counting masks
                    # check if mask is 
                    if type(mask) == str:
                        if os.path.exists(self.joinpath(directory,mask)) and self._is_valid_extension(self.joinpath(directory,mask)):
                            self.segmentation_files.append(self.joinpath(directory,mask))
                            self.seg_mask_status.append(2) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'Found mask for {img}')
                        elif self._is_valid_extension(self.joinpath(directory,mask)) and not os.path.exists(self.joinpath(directory,mask)):
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(1) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'Cannot load mask for {img}, check path')
                        else:
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(0) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'No mask provided for {img}')
                    else:
                        self.segmentation_files.append("")
                        self.seg_mask_status.append(0)
                        logger.info(f'No mask provided for {img}')
                else:
                    logger.info(f'File {img} does not exist or has wrong extension, skipping')                   
                # ToDo: write to log how many files were found, how many masks were found 
                
                
    
        # case 2: no mapper found → detect images + DICOM
        else:
            logger.info('No mappings between files and masks')
            # processed_files = set()


            valid_files = []
            for file in os.listdir(directory):
                full_path = os.path.join(directory, file)
                if os.path.isfile(full_path) and file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    if '_mask' not in file.lower():
                        valid_files.append(full_path)
            


                base = os.path.splitext(file)[0]

                possible_masks = [
                    os.path.join(directory, base + "_mask.nrrd"),
                    os.path.join(directory, base + "_mask.nii.gz"),
                    os.path.join(directory, base + "_mask.nii"),
                ]

                mask_found = next((m for m in possible_masks if os.path.exists(m)), None)

                if mask_found:
                    self.segmentation_files.append(mask_found)
                    self.seg_mask_status.append(2)
                    logger.info(f"Found mask for {file}")
                else:
                    self.segmentation_files.append("")
                    self.seg_mask_status.append(0)
                    logger.info(f"No mask for {file}")


        # Group into DM/CM pairs
        self.image_pairs = self._group_image_pairs(valid_files)
        print(self.image_pairs)
        self.n_pairs = len(self.image_pairs)
        
        logger.info(f'Found {self.n_pairs} complete DM/CM pairs')
        
        self.current_index = 0         
        # load the .cvs file with the old annotations or create a new one
        #print("Path exists",os.path.exists(self.joinpath(directory,"annotations.csv")))
        # Check for existing annotations
        ann_path = os.path.join(directory, "annotations.csv")
        if os.path.exists(ann_path):
            ann_csv = pd.read_csv(ann_path, header=None, index_col=False,
                                 names=["base_name", "artifact_type", "dm_artifacts","cm_artifacts", "other", "mask_path", "mask_status"])
            
            completed_bases = set(ann_csv['base_name'].values)
            self.image_pairs = [p for p in self.image_pairs if p['base_name'] not in completed_bases]
            self.n_pairs = len(self.image_pairs)
            logger.info(f'Restored session: {self.n_pairs} pairs remaining')
        
    
        self.ui.status_checked.setText(f"Checked: {self.current_index} / {self.n_pairs}")
        
        if self.n_pairs > 0:
            print("shoudlnow load new im pair")
            self.load_image_pair()

     # ______________________________________________________________________________________________________________________________________ ___________________________________________________________________ 

# 

    
    def setupSideBySideLayout(self, dm_volume, cm_volume):
        """Setup the side-by-side layout with DM on left, CM on right using built-in Slicer layout"""
        # Use built-in side-by-side layout
        lm = slicer.app.layoutManager()
        lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)
        
        def views_ready():
            # In the built-in side-by-side layout, views are named "Red" and "Yellow"
            return lm.sliceWidget("Red") is not None and lm.sliceWidget("Yellow") is not None
        
        def wire_volumes():
            # Red view (left) = DM, Yellow view (right) = CM
            for tag, vol in [("Red", dm_volume), ("Yellow", cm_volume)]:
                sw = lm.sliceWidget(tag)
                if not sw:
                    continue
                    
                logic = sw.sliceLogic()
                comp = logic.GetSliceCompositeNode()
                sn = logic.GetSliceNode()
                
                # Set the background volume
                comp.SetBackgroundVolumeID(vol.GetID())
                comp.SetForegroundVolumeID(None)
                comp.SetLabelVolumeID(None)
                
                # Disable foreground opacity (removes color overlay)
                comp.SetForegroundOpacity(0.0)
                
                # Force axial orientation (also known as transverse/horizontal)
                sn.SetOrientationToAxial()
                sn.UpdateMatrices()
                
                # Reset the slice viewer to grayscale (remove Red/Yellow tint)
                displayNode = vol.GetDisplayNode()
                if displayNode:
                    displayNode.SetAndObserveColorNodeID("vtkMRMLColorTableNodeGrey")
                
                # Fit the view to the image
                logic.FitSliceToAll()
                
                # Apply a slight zoom
                fov = sn.GetFieldOfView()
                sn.SetFieldOfView(fov[0]*1.0, fov[1]*1.0, fov[2])
        
        def poll():
            if views_ready():
                wire_volumes()
            else:
                qt.QTimer.singleShot(50, poll)
        
        qt.QTimer.singleShot(0, poll)


    def load_image_pair(self):
        """Load a pair of DM and CM images side by side"""
        print(f"[DEBUG] load_image_pair called - _is_loading={self._is_loading}, index={self.current_index}")
        
        if self._is_loading:
            print(f"[DEBUG] Already loading, skipping load_image_pair")
            return
        self._is_loading = True
        
        try:
            if self.current_index >= self.n_pairs:
                print(f"[DEBUG] Index {self.current_index} >= n_pairs {self.n_pairs}, showing completion message")
                qt.QMessageBox.information(
                    slicer.util.mainWindow(), 
                    "Complete", 
                    "All image pairs have been reviewed!"
                )
                self._is_loading = False
                return
            
            logger = logging.getLogger('CEMArtifacts')
            current_pair = self.image_pairs[self.current_index]
            
            print(f"[DEBUG] Loading pair: {current_pair['base_name']}")
            print(f"[DEBUG] DM: {current_pair['DM']}")
            print(f"[DEBUG] CM: {current_pair['CM']}")
            
            # Clean up previous volumes
            slicer.app.layoutManager().setRenderPaused(True)
            
            try:
                if hasattr(self, 'segmentEditorWidget'):
                    self.segmentEditorWidget.setSegmentationNode(None)
                    self.segmentEditorWidget.setSourceVolumeNode(None)
                
                for pair in self.volume_pairs.values():
                    for node in pair.values():
                        if node and slicer.mrmlScene.IsNodePresent(node):
                            slicer.mrmlScene.RemoveNode(node)
                
                self.volume_pairs = {}


                if self.segmentation_node and slicer.mrmlScene.IsNodePresent(self.segmentation_node):
                    slicer.mrmlScene.RemoveNode(self.segmentation_node)
                self.segmentation_node = None
                
                slicer.app.processEvents()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            
            slicer.util.resetSliceViews()

            # Load DM and CM images
            dm_path = current_pair['DM']
            cm_path = current_pair['CM']
            
            readerFactory = vtk.vtkImageReader2Factory()
            
            # Load DM image
            print(f"[DEBUG] Loading DM image...")
            dm_reader = readerFactory.CreateImageReader2(dm_path)
            if dm_reader:
                dm_reader.SetFileName(dm_path)
                dm_reader.Update()
                
                # Check number of components to determine volume type
                num_components = dm_reader.GetOutput().GetNumberOfScalarComponents()
                print(f"[DEBUG] DM image has {num_components} components")
                
                # Use ScalarVolume for grayscale (1 component) or Vector for RGB (3+ components)
                if num_components == 1:
                    dm_volume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
                else:
                    dm_volume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLVectorVolumeNode")
                
                dm_volume.SetName(f"{current_pair['base_name']}_DM")
                dm_volume.SetAndObserveImageData(dm_reader.GetOutput())
                dm_volume.SetSpacing(1, 1, 1)
                dm_volume.CreateDefaultDisplayNodes()  # Create display node
                print(f"[DEBUG] DM volume loaded: {dm_volume.GetName()} ({num_components} components)")
            else:
                raise Exception(f"Could not load DM image: {dm_path}")

            # Load CM image
            print(f"[DEBUG] Loading CM image...")
            cm_reader = readerFactory.CreateImageReader2(cm_path)
            if cm_reader:
                cm_reader.SetFileName(cm_path)
                cm_reader.Update()
                
                # Check number of components to determine volume type
                num_components = cm_reader.GetOutput().GetNumberOfScalarComponents()
                print(f"[DEBUG] CM image has {num_components} components")
                
                # Use ScalarVolume for grayscale (1 component) or Vector for RGB (3+ components)
                if num_components == 1:
                    cm_volume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
                else:
                    cm_volume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLVectorVolumeNode")
                
                cm_volume.SetName(f"{current_pair['base_name']}_CM")
                cm_volume.SetAndObserveImageData(cm_reader.GetOutput())
                cm_volume.SetSpacing(1, 1, 1)
                cm_volume.CreateDefaultDisplayNodes()  # Create display node
                print(f"[DEBUG] CM volume loaded: {cm_volume.GetName()} ({num_components} components)")
            else:
                raise Exception(f"Could not load CM image: {cm_path}")
     
            # Store volume pair
            self.volume_pairs[current_pair['base_name']] = {
                'DM': dm_volume,
                'CM': cm_volume
            }

            print(f"[DEBUG] Setting up side-by-side layout...")
            
            # Setup side-by-side layout
            self.setupSideBySideLayout(dm_volume, cm_volume)

            print(f"[DEBUG] Layout setup complete")
            
            logger.info(f"Loaded pair: {current_pair['base_name']}")
            
            # Resume rendering
            slicer.app.layoutManager().setRenderPaused(False)
            slicer.app.processEvents()
            
            print(f"[DEBUG] load_image_pair completed successfully")
            self._is_loading = False
            return 1
            
        except Exception as e:
            logger = logging.getLogger('CEMArtifacts')
            logger.error(f"Failed to load image pair: {e}")
            print(f"[DEBUG] ERROR in load_image_pair: {e}")
            import traceback
            traceback.print_exc()
            qt.QMessageBox.critical(
                slicer.util.mainWindow(),
                "Load Error",
                f"Could not load image pair\nError: {str(e)}"
            )
            slicer.app.layoutManager().setRenderPaused(False)
            self._is_loading = False
            return 0
        
        finally:
            self._is_loading = False

    def _numerical_status_to_str(self, status):
        return {0: "No mask found", 1: "Cannot load mask", 2: "Mask loaded, no edits", 3:"Mask edited"}[status]   
    
    def _artifacts_to_str(self, artifact_ids):
        mapping = {
            1: "Breast in Breast",
            2: "Skin Line/Thickening",
            3: "Ripple (Motion)",
            4: "Blood Vessels",
            5: "Calcifications",
            6: "Surgical Clip",
            7: "Air Trapping",
            8: "Contrast Splatter",
            9: "Other"
        }
        return ", ".join([mapping[i] for i in artifact_ids])
    #DO these have to be ina ccordance iwht button from .ui? ie or is labels for csv files?
# ______________________________________________________________________________________________________________________________________ ___________________________________________________________________ 

    def save_and_next_clicked(self):
        if self._is_loading:
            return
        


        try:
            # 1. Get artifact presence status
            dm_artifacts_present = self.ui.radioButton_dm_yes.isChecked()
            cm_artifacts_present = self.ui.radioButton_cm_yes.isChecked()
            dm_no_artifacts = self.ui.radioButton_dm_no.isChecked()
            cm_no_artifacts = self.ui.radioButton_cm_no.isChecked()
            
            # Check if user made selections
            if not (dm_artifacts_present or dm_no_artifacts) or not (cm_artifacts_present or cm_no_artifacts):
                # slicer.util.warningDisplay("Please indicate artifact presence for both DM and CM images.")
                return
            
            # 2. Build annotation strings
            dm_annotation = "No artifact"
            cm_annotation = "No artifact"
            artifact_type = "none"
            

            if not dm_artifacts_present and not cm_artifacts_present:
                # Both have no artifacts
                dm_annotation = "No artifact"
                cm_annotation = "No artifact"
                artifact_type = "none"
            else:
                # Collect DM artifacts
                dm_artifact_list = []
                if dm_artifacts_present:
                    for i in range(1, 10):
                        checkbox = getattr(self.ui, f"checkBox_dm_{i}")
                        if checkbox.isChecked():
                            dm_artifact_list.append(i)
                    
                    if not dm_artifact_list:
                        slicer.util.warningDisplay("You indicated DM has artifacts but didn't select any types.")
                        return
                    
                    dm_annotation = self._artifacts_to_str(dm_artifact_list)
                
                # Collect CM artifacts
                cm_artifact_list = []
                if cm_artifacts_present:
                    for i in range(1, 10):
                        checkbox = getattr(self.ui, f"checkBox_cm_{i}")
                        if checkbox.isChecked():
                            cm_artifact_list.append(i)
                    
                    if not cm_artifact_list:
                        slicer.util.warningDisplay("You indicated CM has artifacts but didn't select any types.")
                        return
                    
                    cm_annotation = self._artifacts_to_str(cm_artifact_list)
                
                # Determine artifact type
                if dm_artifact_list and cm_artifact_list:
                    if set(dm_artifact_list) == set(cm_artifact_list):
                        artifact_type = "similar"
                    else:
                        artifact_type = "both_different"
                elif dm_artifact_list:
                    artifact_type = "only_dm"
                elif cm_artifact_list:
                    artifact_type = "only_cm"
            
            # 3. Save comment
            comment_text = self.ui.comment.toPlainText()
            current_pair = self.image_pairs[self.current_index]
            base_name = current_pair['base_name']
            # 4. Determine mask path to save - ALWAYS save a mask
            mask_path_str = ""
            mask_status_str = "No mask"

            if artifact_type == "none":
                # Save empty mask for both DM and CM
                dm_mask_path = self._save_empty_mask(base_name, "_DM")
                cm_mask_path = self._save_empty_mask(base_name, "_CM")
                mask_path_str = f"{os.path.basename(dm_mask_path)}, {os.path.basename(cm_mask_path)}"
                mask_status_str = "Empty mask saved"
            elif dm_artifacts_present or cm_artifacts_present:
                current_pair = self.image_pairs[self.current_index]
                base_name = current_pair['base_name']
                
                # For both_different, check for both DM and CM masks
                if artifact_type == "both_different":
                    dm_npy = f"mask_{base_name}_DM.npy"
                    cm_npy = f"mask_{base_name}_CM.npy"
                    dm_exists = os.path.exists(os.path.join(self.directory, dm_npy))
                    cm_exists = os.path.exists(os.path.join(self.directory, cm_npy))
                    
                    if dm_exists and cm_exists:
                        mask_path_str = f"{dm_npy}, {cm_npy}"
                        mask_status_str = "Mask saved"
                        current_pair['masks']['DM'] = os.path.join(self.directory, dm_npy)
                        current_pair['masks']['CM'] = os.path.join(self.directory, cm_npy)
                    else:
                        mask_status_str = "No mask saved - please use 'Save Outline' button"
                else:
                    # For only_dm, only_cm, or similar
                    if artifact_type == "only_dm":
                        suffix = "_DM"
                    elif artifact_type == "only_cm":
                        suffix = "_CM"
                    else:  # similar
                        suffix = ""
                    
                    npy_filename = f"mask_{base_name}{suffix}.npy"
                    npy_path = os.path.join(self.directory, npy_filename)
                    
                    if os.path.exists(npy_path):
                        mask_path_str = npy_filename
                        mask_status_str = "Mask saved"
                        if 'masks' not in current_pair:
                            current_pair['masks'] = {'DM': None, 'CM': None, 'shared': None}
                        
                        if suffix == "_DM":
                            current_pair['masks']['DM'] = npy_path
                        elif suffix == "_CM":
                            current_pair['masks']['CM'] = npy_path
                        else:
                            current_pair['masks']['shared'] = npy_path
                    else:
                        mask_status_str = "No mask saved - please use 'Save Outline' button"
            # Append to CSV
            data = {
                'base_name': [current_pair['base_name']],
                'artifact_type': [artifact_type],
                'dm_artifacts': [dm_annotation],
                'cm_artifacts': [cm_annotation],
                'other': [comment_text],
                'mask_path': [mask_path_str],
                'mask_status': [mask_status_str]
            }

            df = pd.DataFrame(data)
            df.to_csv(self.joinpath(self.directory, "annotations.csv"),
                    mode='a', index=False, header=False)
            
            # 5. RESET UI BEFORE LOADING NEXT IMAGE
            # Reset DM artifact checkboxes
            for i in range(1, 10):
                getattr(self.ui, f"checkBox_dm_{i}").setChecked(False)
            
            # Reset CM artifact checkboxes
            for i in range(1, 10):
                getattr(self.ui, f"checkBox_cm_{i}").setChecked(False)
            
            # Reset DM presence radio buttons
            self.dmPresentGroup.setExclusive(False)
            self.ui.radioButton_dm_yes.setChecked(False)
            self.ui.radioButton_dm_no.setChecked(False)
            self.dmPresentGroup.setExclusive(True)
            
            # Reset CM presence radio buttons
            self.cmPresentGroup.setExclusive(False)
            self.ui.radioButton_cm_yes.setChecked(False)
            self.ui.radioButton_cm_no.setChecked(False)
            self.cmPresentGroup.setExclusive(True)
            
            self.ui.comment.clear()
            slicer.app.processEvents()
            
            # Move to next pair
            if self.current_index >= self.n_pairs - 1:
                print("All pairs checked")
                qt.QMessageBox.information(
                    slicer.util.mainWindow(),
                    "Complete",
                    "All image pairs have been reviewed!"
                )
                return
            else:
                self.current_index += 1
                self.load_image_pair()
            
            self.ui.status_checked.setText(
                f"Checked: {self.current_index} / {self.n_pairs}"
            )

        finally:
            self._is_loading = False


    def store_current_window_level_settings(self):
        """Store current HU window and level settings."""
        self.window_level = (self.volume_node.GetDisplayNode().GetWindow(), self.volume_node.GetDisplayNode().GetLevel())

    def restore_window_level_settings(self):
        if not self.volume_node: #added this as recommendation
            return

        if not self.volume_node.GetDisplayNode(): #added this as recommendation
            return
        
        if self.window_level is not None:
            self.volume_node.GetDisplayNode().SetAutoWindowLevel(False)
            self.volume_node.GetDisplayNode().SetWindow(self.window_level[0])
            self.volume_node.GetDisplayNode().SetLevel(self.window_level[1])
        else:
            self.volume_node.GetDisplayNode().SetAutoWindowLevel(True)

    def store_segment_visiblity_states(self):
        """Store the visibility states of mask labels."""
        for segment_id in self.segmentation_node.GetSegmentation().GetSegmentIDs():
            visibility = self.segmentation_node.GetDisplayNode().GetSegmentVisibility(segment_id)
            self.segment_visiblity_states[segment_id] = visibility

    def restore_segment_visiblity_states(self):
        """Restore the visibility states of mask labels.""" 
        for segment_id in self.segmentation_node.GetSegmentation().GetSegmentIDs():
            visibility = self.segment_visiblity_states.get(segment_id, True)
            self.segmentation_node.GetDisplayNode().SetSegmentVisibility(segment_id, visibility)


    def set_segmentation_and_mask_for_segmentation_editor(self):
        slicer.app.processEvents()
        
        # Set up segment editor widget
        self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
        self.segmentEditorWidget.setMRMLSegmentEditorNode(slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode"))
        self.segmentEditorWidget.setSegmentationNode(self.segmentation_node)
        self.segmentEditorWidget.setSourceVolumeNode(self.volume_node)
        
        # Compute centroids and jump to them
        segStatLogic = SegmentStatistics.SegmentStatisticsLogic()
        segStatLogic.getParameterNode().SetParameter("Segmentation", self.segmentation_node.GetID())
        segStatLogic.getParameterNode().SetParameter("LabelmapSegmentStatisticsPlugin.centroid_ras.enabled", str(True))
        segStatLogic.computeStatistics()
        stats = segStatLogic.getStatistics()
        
        self.pointListNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode")
        self.pointListNode.CreateDefaultDisplayNodes()
        
        markupsLogic = slicer.modules.markups.logic()
        for segmentId in stats["SegmentIDs"]:
            if self.segment_visiblity_states.get(segmentId, True):
                centroid_ras = stats[segmentId, "LabelmapSegmentStatisticsPlugin.centroid_ras"]
                markupsLogic.JumpSlicesToLocation(*centroid_ras, False)

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()
        #self.effectFactorySingleton.disconnect("effectRegistered(QString)", self.editorEffectRegistered)

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
        self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    def onSceneStartClose(self, caller, event):
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        try:
            self.setParameterNode(None)
            self.segmentEditorWidget.setSegmentationNode(None)
            self.segmentEditorWidget.removeViewObservations()
        except:
            pass

    def onSceneEndClose(self, caller, event):
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()
            self.selectParameterNode()
            self.segmentEditorWidget.updateWidgetFromMRML()  
        
    def onSceneEndImport(self, caller, event):
        if self.parent.isEntered:
            self.selectParameterNode()
            self.segmentEditorWidget.updateWidgetFromMRML()

    def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        # Select default input nodes if nothing is selected yet to save a few clicks for the user
        if not self._parameterNode.GetNodeReference("InputVolume"):
            firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
            if firstVolumeNode:
                self._parameterNode.SetNodeReferenceID("InputVolume", firstVolumeNode.GetID())

    def setParameterNode(self, inputParameterNode):
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """
        #if inputParameterNode:
        #    self.logic.setDefaultParameters(inputParameterNode)
        
        if self._parameterNode is not None:
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True
        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

        self._parameterNode.EndModify(wasModified)
# SlicerLikertDLratingLogic
#

class SlicerLikertDLratingLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

    
#
# SlicerLikertDLratingTest
#

class SlicerLikertDLratingTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_SlicerLikertDLrating1()

    def test_SlicerLikertDLrating1(self):
 

        self.delayDisplay("Starting the test")

        self.delayDisplay('Test passed')

# At the very end of CEMArtifacts.py, add:
if __name__ == "__main__":
    import sys
    
    # Instantiate and show the module widget
    parent = slicer.qMRMLWidget()
    parent.show()
    widget = CEMArtifactsWidget(parent)
    widget.setup()