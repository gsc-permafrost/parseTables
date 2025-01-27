import os
import yaml
import numpy as np
import pandas as pd
import dateutil.parser as dateParse
from dataclasses import dataclass,field
# Requires a csv file output by a HOBO logger
# self.modes:
# 1 - Parse Metadata
# 2 - Read data and dump to numpy array
# 3 - Read data and dump to a timestamped pandas dataframe
# saveTo: self.mode must == 2, save a TOA5 file to specified directory with timestamp in name following format output by card convert
# Timezone: Optionally added to Metadata
# Clip: Optionally limit output to rows[:clip], only needed for small tables which don't fill a frame

# Key elements:
# Metadata - dict of header information
# Data - numpy array or pandas timestamped dataframe depending on self.mode
# Timestamp - numpy array in POSIX format from logger time

def load():
    c = os.path.dirname(os.path.abspath(__file__))
    pth = os.path.join(c,'config_files','defaultMetadata.yml')
    with open(pth,'r') as f:
        defaults = yaml.safe_load(f)
    return(defaults)
@dataclass
class Metadata:
    log: bool = False
    verbose: bool = False
    mode: int = 1
    Metadata: dict = field(default_factory=load)
    Contents: dict = field(default_factory=dict)

class parseHoboCSV(Metadata):
    def __init__(self,**kwds):
        super().__init__(**kwds)
        
    def parse(self,file,saveTo=None):
        if not file.endswith('.csv'):
            self.mode = 0
            return 
        self.f = open(file,'r',encoding='utf-8-sig')
        T = self.f.readline().rstrip('\n')
        if T.startswith('"Plot Title: '):
            self.isHobo = True
        else:
            self.isHobo = False
            self.mode = 0
        if self.mode >= 1:
            self.Metadata['Type'] = 'HOBO-readout'
            fn = os.path.split(file)[-1].rsplit('.',1)[0].split('-')
            self.Metadata['StationName']=fn[1].rsplit('.',1)[0]
            self.Metadata['SerialNo']=fn[0]
            ts =  T.split('.')[-1].rstrip('"')
            if len(ts)<= 6:
                self.Metadata['Timestamp'] = pd.to_datetime(ts,format='%y%m%d').strftime('%Y-%m-%dT%H%M')
            else:
                print('!!!',ts)
                self.Metadata['Timestamp'] = ts
            self.Metadata['Program'] = T.replace('"','').split('Plot Title: ')[-1]
            self.parseHeader()        
        self.f.close()
        if self.mode >= 2:
            self.Data = self.Data.select_dtypes('float32').values
        if self.mode == 3:
            self.Data = pd.DataFrame(self.Data)
            self.Data.columns = self.Header.loc[:,self.Header.loc['dataType'] == 'float32'].columns
            self.Timestamp = pd.to_datetime(self.Timestamp,unit='s')
            self.Data.index=self.Timestamp.round(self.Metadata['Frequency'])
            self.Data.index.name = 'TIMESTAMP'
        elif self.mode == 4:
            print(self.Data)
    
    def parseHeader(self):
        H = self.f.readline()
        H = H.replace('#','RecordNumber').lstrip('"').rstrip('"\n').split('","')
        H = [h.lstrip().rstrip(')').replace('(',',').split(',') for h in H]
        L = [len(h) for h in H]
        data = [h if l == max(L) else [sh for sh in h] + ['' for i in range(max(L)-l)] for h,l in zip(H,L)]
        # data = [[sh for sh in h] + ['' for i in range(max(L)-l)] for h,l in zip(H,L)]
        self.Header = pd.DataFrame(data = data).T
        self.Header.columns = self.Header.iloc[0].values+self.Header.iloc[-1].values
        self.Header.columns = self.Header.columns.str.replace(' ','_').str.replace(':','').str.rstrip('_')
        self.Header = self.Header[1:-1].copy()
        self.Header.index.name=''
        self.Header.index = ['unit_in','logger','sensor']
        self.Header.loc['ignore',:]=True
        self.statusCols = ['Host_Connected', 'Stopped', 'End_Of_File']
        self.statusCols = self.Header.columns[self.Header.columns.isin(self.statusCols)]
        self.readData()
        self.Header.loc['dataType'] = [str(v) for v in self.Data.dtypes.values]
        self.Header.loc['ignore',:]=(self.Header.loc['dataType']!='float32').values
        self.Contents = self.Header.to_dict()
        self.Metadata['Frequency'] = str(int(np.median(np.diff(self.Timestamp))))+'s'
        self.Metadata['Timezone'] = self.Header['Date_Time']['unit_in'].lstrip()
        
    def readData(self):
        self.Data = pd.read_csv(self.f,header=None)
        self.Data.columns = self.Header.columns
        self.Data[self.statusCols] = self.Data[self.statusCols].ffill(limit=1)
        keep = pd.isna(self.Data[self.statusCols]).all(axis=1)
        self.Data = self.Data.loc[keep].copy()
        # Convert default 64-bit values to 32-bit
        self.Data = self.Data.astype({col:'float32' for col in self.Data.select_dtypes('float64').columns})
        self.Data = self.Data.astype({col:'int32' for col in self.Data.select_dtypes('int64').columns})
        self.Timestamp = np.array([dateParse.parse(x).timestamp() for x in self.Data['Date_Time']])
        

